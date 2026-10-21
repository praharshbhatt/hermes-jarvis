"""Brains against fake HTTP servers: streaming, sessions, profiles, keys, health checks."""
import asyncio
import json

from aiohttp import web
from aiohttp.test_utils import TestServer

from hermes_jarvis import config
from hermes_jarvis.brains import make_brain
from hermes_jarvis.brains.hermes import HermesBrain
from hermes_jarvis.brains.openai_compat import OpenAIBrain
from hermes_jarvis.settings import settings


def sse(*chunks, tool=None):
    out = ""
    for c in chunks:
        out += "data: " + json.dumps({"choices": [{"delta": {"content": c}}]}) + "\n\n"
    if tool:
        out = f"event: hermes.tool.progress\ndata: {json.dumps(tool)}\n\n" + out
    return ": keepalive\n\n" + out + "data: [DONE]\n\n"


async def collect(agen):
    return [e async for e in agen]


def test_make_brain_picks_by_config():
    assert isinstance(make_brain(), HermesBrain)
    config.use({"brain": {"type": "openai"}})
    assert isinstance(make_brain(), OpenAIBrain)
    config.use({"brain": {"type": "nope"}})
    try:
        make_brain()
    except ValueError as e:
        assert "unknown brain.type" in str(e)


def test_openai_brain_streams_keeps_history_and_sends_the_key(monkeypatch):
    seen = []

    async def chat(request):
        seen.append((request.headers.get("Authorization"), await request.json()))
        return web.Response(text=sse("<speak>Hi ", "there.</speak>"), content_type="text/event-stream")

    async def go():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", chat)
        async with TestServer(app) as srv:
            monkeypatch.setenv("MY_KEY", "sekret")
            config.use({"brain": {"type": "openai", "base_url": str(srv.make_url("/")), "model": "m",
                                  "api_key_env": "MY_KEY"}, "user": {"name": "Ada"}},
                       base_dir=config.cfg.base_dir)
            brain = OpenAIBrain()
            first = await collect(brain.turn("hello"))
            sid = first[0]["id"]
            second = await collect(brain.turn("and again", sid))
            await brain.close()
            return first, second, sid

    first, second, sid = asyncio.run(go())
    assert first[0]["type"] == "session" and sid.startswith("oc-")
    assert "".join(e["delta"] for e in first if e["type"] == "text") == "<speak>Hi there.</speak>"
    assert first[-1]["type"] == "done"
    auth, body = seen[0]
    assert auth == "Bearer sekret" and body["model"] == "m" and body["stream"] is True
    system = body["messages"][0]["content"]
    assert "<speak>" in system and "Ada" in system          # voice protocol and the user's name reach the model
    roles = [m["role"] for m in seen[1][1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]  # the second turn carries the first exchange
    assert second[0]["id"] == sid


def test_openai_brain_reports_http_errors_and_keeps_going():
    async def chat(request):
        return web.Response(status=401, text="bad key")

    async def go():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", chat)
        async with TestServer(app) as srv:
            config.use({"brain": {"type": "openai", "base_url": str(srv.make_url("/"))}}, base_dir=config.cfg.base_dir)
            brain = OpenAIBrain()
            ev = await collect(brain.turn("hi"))
            await brain.close()
            return ev

    ev = asyncio.run(go())
    assert ev[-1]["type"] == "error" and ev[-1]["status"] == 401


def test_openai_history_survives_a_restart():
    async def chat(request):
        return web.Response(text=sse("ok"), content_type="text/event-stream")

    async def go():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", chat)
        async with TestServer(app) as srv:
            config.use({"brain": {"type": "openai", "base_url": str(srv.make_url("/"))}}, base_dir=config.cfg.base_dir)
            a = OpenAIBrain()
            sid = (await collect(a.turn("remember this")))[0]["id"]
            await a.close()
            b = OpenAIBrain()  # a new process reads the saved file
            return sid, b._sessions

    sid, sessions = asyncio.run(go())
    assert sid in sessions and sessions[sid][0]["content"] == "remember this"


def test_hermes_brain_profiles_keys_sessions_and_tool_events(monkeypatch):
    calls = []

    async def chat_default(request):
        calls.append(("default", request.headers.get("Authorization"), request.headers.get("X-Hermes-Session-Id")))
        return web.Response(text=sse("<speak>One.</speak>", tool={"tool": "terminal", "status": "running"}),
                            content_type="text/event-stream", headers={"X-Hermes-Session-Id": "api-abc"})

    async def chat_work(request):
        calls.append(("work", request.headers.get("Authorization"), (await request.json())["model"]))
        return web.Response(text=sse("<speak>Two.</speak>"), content_type="text/event-stream",
                            headers={"X-Hermes-Session-Id": "api-work"})

    async def sessions(request):
        calls.append(("sessions", request.query.get("source"), request.query.get("limit")))
        return web.json_response({"data": [{"id": "a", "last_active": 1}, {"id": "b", "last_active": 5}]})

    async def go():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", chat_default)
        app.router.add_post("/p/work/v1/chat/completions", chat_work)
        app.router.add_get("/api/sessions", sessions)
        async with TestServer(app) as srv:
            config.use({"brain": {"base_url": str(srv.make_url("/"))}}, base_dir=config.cfg.base_dir)
            monkeypatch.setenv("HERMES_API_KEY", "k-default")
            monkeypatch.setenv("HERMES_API_KEY_WORK", "k-work")
            brain = HermesBrain()
            a = await collect(brain.turn("hi", "api-prev"))
            b = await collect(brain.turn("hi", None, "work"))
            s = await brain.list_sessions("default", 10, "api_server")
            await brain.close()
            return a, b, s

    a, b, s = asyncio.run(go())
    assert a[0] == {"type": "session", "id": "api-abc"}
    assert any(e["type"] == "tool" and e["tool"] == "terminal" for e in a)
    assert calls[0] == ("default", "Bearer k-default", "api-prev")      # continued session header and default key
    assert calls[1] == ("work", "Bearer k-work", "work")                # profile path, its own key, model = profile
    assert calls[2] == ("sessions", "api_server", "10") and [x["id"] for x in s] == ["b", "a"]  # newest first


def test_hermes_check_names_the_missing_profile_key(monkeypatch):
    async def health(request):
        return web.json_response({"status": "ok"})

    async def models(request):
        return web.json_response({"data": []}) if request.headers.get("Authorization") == "Bearer good" \
            else web.Response(status=401)

    async def go():
        app = web.Application()
        app.router.add_get("/health", health)
        app.router.add_get("/v1/models", models)
        async with TestServer(app) as srv:
            config.use({"brain": {"base_url": str(srv.make_url("/"))}}, base_dir=config.cfg.base_dir)
            settings.update({"profiles": [
                {"name": "default", "is_default": True, "enabled": True},
                {"name": "work", "is_default": False, "enabled": True}]})
            monkeypatch.setenv("HERMES_API_KEY", "good")
            brain = HermesBrain()
            res = await brain.check()
            await brain.close()
            return res

    res = {label: (ok, detail) for label, ok, detail in asyncio.run(go())}
    assert res["Hermes gateway reachable"][0] is True
    assert res["Hermes profile 'default' key"][0] is True
    ok, detail = res["Hermes profile 'work' key"]
    assert ok is False and "HERMES_API_KEY_WORK" in detail
