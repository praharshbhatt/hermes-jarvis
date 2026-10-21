"""Routing: window rule, Jev decisions with thresholds, and every fallback, against a fake Jev server."""
import asyncio
import time

from aiohttp import web
from aiohttp.test_utils import TestServer

from hermes_jarvis import router as router_mod
from hermes_jarvis.router import Router
from hermes_jarvis.settings import settings

PROFILES = [{"name": "default", "is_default": True, "enabled": True, "description": "general"},
            {"name": "work", "is_default": False, "enabled": True, "description": "clients and invoices"}]


class FakeBrain:
    name = "fake"
    supports_profiles = supports_sessions = True

    def __init__(self):
        self.listed = []

    async def list_sessions(self, profile="default", limit=100, source=None):
        self.listed.append((profile, source))
        now = time.time()
        return {"default": [{"id": "api-goals", "title": "Goals note heading", "last_active": now - 600}],
                "work": [{"id": "api-inv", "title": "October invoice status", "last_active": now - 300},
                         {"id": "api-hidden", "title": "x", "last_active": now, "hidden": True},
                         {"id": "api-untitled", "title": "", "last_active": now}]}[profile]


def with_jev(answers, fn, status=200):
    async def decisions(request):
        decisions.body = await request.json()
        if status != 200:
            return web.Response(status=status, text="boom")
        return web.json_response({"answers": answers})

    async def go():
        app = web.Application()
        app.router.add_post("/decide", decisions)
        async with TestServer(app) as srv:
            router_mod.JEV_URL = str(srv.make_url("/decide"))
            r = Router(FakeBrain())
            try:
                return await fn(r), decisions
            finally:
                await r.close()

    return asyncio.run(go())


def setup(monkeypatch, profiles=PROFILES):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    settings.update({"profiles": profiles})


def test_within_the_window_no_model_is_called(monkeypatch):
    setup(monkeypatch)
    out, dec = with_jev({}, lambda r: r.route("anything", "api-cur", "work", time.time() - 60))
    assert (out.profile, out.session_id, out.reason) == ("work", "api-cur", "window")
    assert not hasattr(dec, "body")


def test_resume_a_matching_conversation(monkeypatch):
    setup(monkeypatch)
    ans = {"session": {"choice": "api-inv", "probabilities": {"new": 0.05, "api-inv": 0.9, "api-goals": 0.05}},
           "profile": {"choice": "work", "probabilities": {"default": 0.1, "work": 0.9}}}
    out, dec = with_jev(ans, lambda r: r.route("status of that invoice", None, "default", 0))
    assert (out.profile, out.session_id, out.reason) == ("work", "api-inv", "jev-resume")
    crit = dec.body["questions"]["session"]["criteria"]
    assert set(crit) == {"new", "api-goals", "api-inv"}               # hidden and untitled sessions are not offered
    assert "[work] October invoice status" in crit["api-inv"]
    assert dec.body["questions"]["profile"]["criteria"]["work"] == "clients and invoices"


def test_low_session_probability_starts_a_new_one_in_the_best_profile(monkeypatch):
    setup(monkeypatch)
    ans = {"session": {"choice": "api-inv", "probabilities": {"new": 0.4, "api-inv": 0.6}},
           "profile": {"choice": "work", "probabilities": {"default": 0.1, "work": 0.9}}}
    out, _ = with_jev(ans, lambda r: r.route("hm", None, "default", 0))
    assert (out.profile, out.session_id, out.reason) == ("work", None, "jev-new")


def test_unsure_profile_falls_back_to_the_default(monkeypatch):
    setup(monkeypatch)
    ans = {"session": {"choice": "new", "probabilities": {"new": 1}},
           "profile": {"choice": "work", "probabilities": {"default": 0.45, "work": 0.55}}}
    out, _ = with_jev(ans, lambda r: r.route("hm", None, "default", 0))
    assert out.profile == "default" and out.session_id is None


def test_a_single_profile_asks_no_profile_question(monkeypatch):
    setup(monkeypatch, PROFILES[:1])
    ans = {"session": {"choice": "new", "probabilities": {"new": 1}}}
    out, dec = with_jev(ans, lambda r: r.route("hello", None, "default", 0))
    assert "profile" not in dec.body["questions"] and out.profile == "default"


def test_ignore_window_for_the_tester(monkeypatch):
    setup(monkeypatch)
    ans = {"session": {"choice": "new", "probabilities": {"new": 1}}, "profile": {"choice": "default", "probabilities": {"default": 1}}}
    out, dec = with_jev(ans, lambda r: r.route("hi", "api-cur", "work", time.time(), ignore_window=True))
    assert out.reason == "jev-new" and hasattr(dec, "body")


def test_failures_never_block_a_reply(monkeypatch):
    setup(monkeypatch)
    out, _ = with_jev({}, lambda r: r.route("hi", None, "work", 0), status=500)
    assert (out.profile, out.session_id) == ("default", None) and out.reason.startswith("fallback:")


def test_router_is_off_without_a_key_or_with_a_brain_that_cannot_list_sessions(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    r = Router(FakeBrain())
    assert r.available() is False
    out = asyncio.run(r.route("hi", None, "work", 0))
    assert (out.profile, out.session_id, out.reason) == ("default", None, "disabled")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert r.available() is True
    FakeBrain.supports_sessions = False
    try:
        assert Router(FakeBrain()).available() is False
    finally:
        FakeBrain.supports_sessions = True
