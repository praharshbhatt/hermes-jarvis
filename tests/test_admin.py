"""The web UI server: login, sessions, CSRF, headers, live events, static serving, and the onboarding endpoints."""
import asyncio
import base64
import hashlib

import pytest
from webhelpers import (
    PASSWORD,
    FakeBrain,
    FakeBridge,
    FakeSpeaker,
    FakeStt,
    fake_app,
    headers,
    login,
    origin_of,
    with_client,
)

from hermes_jarvis import admin as admin_mod
from hermes_jarvis import config
from hermes_jarvis.admin import AdminServer
from hermes_jarvis.events import bus
from hermes_jarvis.settings import settings


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)


# ---------------------------------------------------------------- login and sessions
def test_the_api_needs_a_session_but_healthz_and_the_session_probe_do_not():
    async def run(c, _s):
        out = {}
        out["health"] = (await c.get("/healthz")).status
        out["probe"] = (await (await c.get("/api/session")).json())["authenticated"]
        for path in ("/api/settings", "/api/status", "/api/turns", "/api/history", "/api/device", "/api/events",
                     "/api/doctor", "/api/voices", "/api/discover"):
            out[path] = (await c.get(path)).status
        return out

    got = with_client(run)
    assert got["health"] == 200 and got["probe"] is False
    assert all(v == 401 for k, v in got.items() if k.startswith("/api/")), got


def test_wrong_credentials_are_refused_and_the_message_does_not_say_which_part(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _: real_sleep(0))

    async def run(c, _s):
        h = {"Origin": origin_of(c)}
        a = await c.post("/api/login", json={"username": "admin", "password": "nope"}, headers=h)
        b = await c.post("/api/login", json={"username": "root", "password": PASSWORD}, headers=h)
        return a.status, (await a.json())["error"], b.status, (await b.json())["error"], c.session.cookie_jar

    sa, ea, sb, eb, jar = with_client(run)
    assert (sa, sb) == (401, 401) and ea == eb and len(list(jar)) == 0


def test_login_sets_a_hardened_cookie_and_returns_a_csrf_token():
    async def run(c, srv):
        r = await c.post("/api/login", json={"username": "admin", "password": PASSWORD}, headers={"Origin": origin_of(c)})
        body = await r.json()
        probe = await (await c.get("/api/session")).json()
        return r.status, r.headers["Set-Cookie"], body, probe

    status, cookie, body, probe = with_client(run)
    assert status == 200 and cookie.startswith("hj_session=")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/" in cookie and "Max-Age=" in cookie
    assert "Secure" not in cookie                                    # plain http on localhost
    assert body["csrf"] == probe["csrf"] and probe["authenticated"] is True and len(body["csrf"]) >= 40


def test_over_https_the_cookie_is_secure_and_host_prefixed_but_only_behind_a_trusted_proxy():
    def attempt(origin_scheme):
        async def run(c, _s):
            h = {"Origin": origin_of(c).replace("http://", origin_scheme + "://"), "X-Forwarded-Proto": "https"}
            return (await c.post("/api/login", json={"username": "admin", "password": PASSWORD}, headers=h)).headers
        return run

    run = attempt("http")  # not behind a trusted proxy: the page really is http, so its Origin is http
    untrusted = with_client(run)
    assert untrusted["Set-Cookie"].startswith("hj_session=") and "Secure" not in untrusted["Set-Cookie"]
    assert "Strict-Transport-Security" not in untrusted              # a spoofed header means nothing by default

    config.use({"admin": {"trust_proxy": True}}, base_dir=config.cfg.base_dir)
    trusted = with_client(attempt("https"))  # behind a TLS proxy a browser sends an https Origin
    assert trusted["Set-Cookie"].startswith("__Host-hj_session=") and "Secure" in trusted["Set-Cookie"]
    assert "HttpOnly" in trusted["Set-Cookie"] and "SameSite=Strict" in trusted["Set-Cookie"]
    assert trusted["Strict-Transport-Security"].startswith("max-age=")


def test_every_login_gets_a_new_session_id_and_the_old_one_stops_working():
    async def run(c, srv):
        await login(c)
        first = c.session.cookie_jar.filter_cookies(c.make_url("/"))["hj_session"].value
        r = await c.post("/api/login", json={"username": "admin", "password": PASSWORD}, headers={"Origin": origin_of(c)})
        second = r.cookies["hj_session"].value
        c.session.cookie_jar.clear()   # replay the old id on its own, as an attacker who kept it would
        stale = await c.get("/api/settings", headers={"Cookie": f"hj_session={first}"})
        fresh = await c.get("/api/settings", headers={"Cookie": f"hj_session={second}"})
        return first, second, (stale.status, fresh.status)

    first, second, (stale, fresh) = with_client(run)
    assert first != second and stale == 401 and fresh == 200


def test_logout_ends_the_session_and_needs_csrf():
    async def run(c, srv):
        csrf = await login(c)
        no_token = await c.post("/api/logout", headers={"Origin": origin_of(c)})
        out = await c.post("/api/logout", headers=headers(c, csrf))
        after = await c.get("/api/settings")
        return no_token.status, out.status, after.status, srv.auth.count()

    assert with_client(run) == (403, 200, 401, 0)


def test_repeated_failures_lock_the_address_out_even_for_the_right_password(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _: real_sleep(0))

    async def run(c, srv):
        h = {"Origin": origin_of(c)}
        for _ in range(srv.auth.LOCKOUT_FAILS):
            assert (await c.post("/api/login", json={"username": "admin", "password": "x"}, headers=h)).status == 401
        locked = await c.post("/api/login", json={"username": "admin", "password": PASSWORD}, headers=h)
        return locked.status, locked.headers.get("Retry-After"), (await c.get("/healthz")).status

    assert with_client(run) == (429, "300", 200)


def test_a_successful_login_clears_the_failure_count(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _: real_sleep(0))

    async def run(c, srv):
        h = {"Origin": origin_of(c)}
        for _ in range(srv.auth.LOCKOUT_FAILS - 1):
            await c.post("/api/login", json={"username": "admin", "password": "x"}, headers=h)
        ok = await c.post("/api/login", json={"username": "admin", "password": PASSWORD}, headers=h)
        return ok.status, srv.auth.locked_out("127.0.0.1")

    assert with_client(run) == (200, False)


def test_polling_does_not_keep_a_session_alive_but_real_requests_do():
    async def run(c, srv):
        await login(c)
        s = next(iter(srv.auth._sessions.values()))
        s.last_seen -= srv.auth.idle_seconds() - 5
        stale = s.last_seen
        await c.get("/api/status", headers={"X-HJ-Background": "1"})
        polled = s.last_seen
        await c.get("/api/status")
        return stale, polled, s.last_seen

    stale, polled, touched = with_client(run)
    assert polled == stale and touched > stale


# ---------------------------------------------------------------- CSRF and origin
def test_changes_need_the_csrf_token():
    async def run(c, _s):
        csrf = await login(c)
        body = {"recent_sessions_count": 4}
        out = {
            "none": (await c.put("/api/settings", json=body, headers={"Origin": origin_of(c)})).status,
            "wrong": (await c.put("/api/settings", json=body, headers=headers(c, "x" * 43))).status,
            "ok": (await c.put("/api/settings", json=body, headers=headers(c, csrf))).status,
        }
        out["value"] = (await (await c.get("/api/settings")).json())["recent_sessions_count"]
        return out

    assert with_client(run) == {"none": 403, "wrong": 403, "ok": 200, "value": 4}


def test_cross_origin_requests_are_refused_even_with_a_valid_session_and_token():
    async def run(c, _s):
        csrf = await login(c)
        out = {}
        for name, h in {
            "evil origin": {"X-CSRF-Token": csrf, "Origin": "http://evil.example"},
            "cross-site fetch": {"X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"},
            "evil login": {"Origin": "http://evil.example"},
        }.items():
            path = "/api/login" if name == "evil login" else "/api/settings"
            r = await c.request("POST" if name == "evil login" else "PUT", path, headers=h,
                                json={"username": "admin", "password": PASSWORD} if name == "evil login"
                                else {"ack_after_s": 3})
            out[name] = r.status
        out["same origin"] = (await c.put("/api/settings", json={"ack_after_s": 3}, headers=headers(c, csrf))).status
        return out

    assert with_client(run) == {"evil origin": 403, "cross-site fetch": 403, "evil login": 403, "same origin": 200}


def test_a_dev_server_origin_can_be_allowed_in_the_config():
    config.use({"admin": {"allowed_origins": ["http://localhost:3000"]}}, base_dir=config.cfg.base_dir)

    async def run(c, _s):
        csrf = await login(c)
        ok = await c.put("/api/settings", json={"ack_after_s": 3}, headers={"X-CSRF-Token": csrf, "Origin": "http://localhost:3000"})
        other = await c.put("/api/settings", json={"ack_after_s": 3}, headers={"X-CSRF-Token": csrf, "Origin": "http://localhost:4000"})
        return ok.status, other.status

    assert with_client(run) == (200, 403)


# ---------------------------------------------------------------- headers
def test_security_headers_are_on_every_response_including_errors():
    async def run(c, _s):
        await login(c)
        seen = []
        for r in (await c.get("/healthz"), await c.get("/api/settings"), await c.get("/api/nothing"),
                  await c.put("/api/settings", json={}, headers={"Origin": origin_of(c)})):  # a 401, a 200, a 404, a 403
            seen.append((r.status, r.headers))
        await c.get("/api/events")  # not read to the end
        return seen

    for status, h in with_client(run):
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY", status
        assert h["Referrer-Policy"] == "no-referrer" and h["Cross-Origin-Opener-Policy"] == "same-origin"
        assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and "microphone=()" in h["Permissions-Policy"]
        assert h["Cache-Control"] == "no-store", status


def test_bodies_must_be_small_json_objects():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        return {
            "text/plain": (await c.put("/api/settings", data="a=1", headers={**h, "Content-Type": "text/plain"})).status,
            "not json": (await c.put("/api/settings", data="{nope", headers={**h, "Content-Type": "application/json"})).status,
            "list": (await c.put("/api/settings", json=[1], headers=h)).status,
            "huge": (await c.put("/api/settings", json={"voice_prompt": "x" * 400_000}, headers=h)).status,
            "long text": (await c.put("/api/settings", json={"voice_prompt": "x" * 25_000}, headers=h)).status,
        }

    assert with_client(run) == {"text/plain": 415, "not json": 400, "list": 400, "huge": 413, "long text": 400}


# ---------------------------------------------------------------- settings through the API
def test_settings_validation_over_the_api():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        out = {}
        for name, body in {"unknown": {"nope": 1}, "range": {"piper_length_scale": 0}, "nan": {"ack_after_s": "nan"},
                           "voice": {"tts_voice": "../../etc/passwd"}, "profiles": {"profiles": []}}.items():
            r = await c.put("/api/settings", json=body, headers=h)
            out[name] = (r.status, "error" in await r.json())
        return out

    assert with_client(run) == {k: (400, True) for k in ("unknown", "range", "nan", "voice", "profiles")}


def test_changing_acks_or_voice_triggers_the_right_follow_up():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        await c.put("/api/settings", json={"canned_acks": "Right away."}, headers=h)
        await asyncio.sleep(0.05)
        first = FakeSpeaker.prerendered
        await c.put("/api/settings", json={"tts_voice": "en_US-ryan-medium"}, headers=h)
        await asyncio.sleep(0.05)
        return first, FakeBridge.voice_applied

    before = FakeBridge.voice_applied
    first, applied = with_client(run)
    assert first == ["Right away."] and applied == before + 1


def test_status_reports_the_brain_profiles_voice_and_onboarding():
    async def run(c, _s):
        await login(c)
        return await (await c.get("/api/status")).json()

    s = with_client(run)
    assert s["brain"]["name"] == "hermes" and s["onboarding_completed"] is False and s["state"] == "idle"
    assert s["voice"] == "en_GB-alan-medium" and s["profile_keys"] == {"default": False}


# ---------------------------------------------------------------- live events
def test_the_event_stream_needs_a_session():
    async def run(c, _s):
        return (await c.get("/api/events")).status

    assert with_client(run) == 401


def test_the_event_stream_sends_a_snapshot_then_live_events():
    async def run(c, _s):
        await login(c)
        bus.set_state("thinking")
        r = await c.get("/api/events")
        assert r.status == 200 and r.headers["Content-Type"].startswith("text/event-stream")
        assert r.headers["Cache-Control"] == "no-store"
        text = b""
        async def read_until(marker: bytes) -> None:
            nonlocal text
            while marker not in text:
                text += await asyncio.wait_for(r.content.readany(), 5)
        await read_until(b"event: snapshot")
        await read_until(b'"state":"thinking"')
        bus.set_state("speaking")
        bus.transcript("assistant", "Good evening.")
        await read_until(b"event: transcript")
        r.close()
        return text.decode()

    out = with_client(run)
    assert "retry: 3000" in out and '"state":"speaking"' in out and "Good evening." in out


def test_the_event_stream_hides_text_when_transcripts_are_off():
    config.use({"privacy": {"save_transcripts": False}}, base_dir=config.cfg.base_dir)

    async def run(c, _s):
        await login(c)
        r = await c.get("/api/events")
        bus.transcript("user", "my secret question")
        text = b""
        while b"event: transcript" not in text:
            text += await asyncio.wait_for(r.content.readany(), 5)
        r.close()
        return text.decode()

    out = with_client(run)
    assert "my secret question" not in out and '"hidden":true' in out


def test_too_many_open_live_views_are_refused():
    async def run(c, srv):
        await login(c)
        next(iter(srv.auth._sessions.values())).streams = 4
        return (await c.get("/api/events")).status

    assert with_client(run) == 429


# ---------------------------------------------------------------- static app and CSP
def test_pages_redirect_to_login_until_signed_in_and_back_afterwards(tmp_path, monkeypatch):
    fake_app(tmp_path, monkeypatch)

    async def run(c, _s):
        out = {}
        r = await c.get("/", allow_redirects=False)
        out["anon /"] = (r.status, r.headers.get("Location"))
        out["anon /settings/"] = (await c.get("/settings/", allow_redirects=False)).status
        out["login page"] = (await c.get("/login/")).status
        await login(c)
        out["authed /"] = (await c.get("/")).status
        r = await c.get("/login/", allow_redirects=False)
        out["authed /login/"] = (r.status, r.headers.get("Location"))
        return out

    assert with_client(run) == {"anon /": (302, "/login/"), "anon /settings/": 302, "login page": 200,
                                "authed /": 200, "authed /login/": (302, "/")}


def test_the_csp_allows_only_this_pages_inline_scripts_by_hash(tmp_path, monkeypatch):
    fake_app(tmp_path, monkeypatch)
    inline = 'self.__next_f.push([1,"b"])'
    digest = base64.b64encode(hashlib.sha256(inline.encode()).digest()).decode()

    async def run(c, _s):
        r = await c.get("/login/")
        return r.headers["Content-Security-Policy"], await r.text()

    csp, html = with_client(run)
    assert f"'sha256-{digest}'" in csp and "script-src 'self'" in csp
    script_src = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
    assert "unsafe-inline" not in script_src and "unsafe-eval" not in script_src
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp and "connect-src 'self'" in csp
    assert "login" in html


def test_built_assets_are_public_immutable_and_correctly_typed(tmp_path, monkeypatch):
    fake_app(tmp_path, monkeypatch)

    async def run(c, _s):
        r = await c.get("/_next/static/x.js")
        return r.status, r.headers["Cache-Control"], r.content_type, await r.text()

    status, cache, ctype, body = with_client(run)
    assert status == 200 and "immutable" in cache and "javascript" in ctype and body == "console.log(1)"


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/_next/../../secret.txt",
                                  "/login/../../secret.txt", "/etc/passwd", "/%00", "/....//secret.txt"])
def test_paths_cannot_escape_the_app_folder(tmp_path, monkeypatch, path):
    fake_app(tmp_path, monkeypatch)

    async def run(c, _s):
        await login(c)
        r = await c.get(path, allow_redirects=False)
        return r.status, await r.read()

    status, body = with_client(run)
    assert b"not for the web" not in body and status in (200, 302, 400, 404)  # never the file outside the folder


def test_an_unbuilt_ui_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_mod, "APP_DIR", tmp_path / "missing")

    async def run(c, _s):
        await login(c)
        r = await c.get("/")
        return r.status, await r.text()

    status, text = with_client(run)
    assert status == 503 and "build_ui.sh" in text


# ---------------------------------------------------------------- admin start-up rules
def test_the_ui_is_off_without_credentials_and_on_with_a_hash(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert asyncio.run(AdminServer(FakeBridge()).start()) is False

    from hermes_jarvis import auth

    async def go():
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", auth.hash_password("pw-for-the-hash", iterations=1000))
        config.use({"admin": {"port": 18777}}, base_dir=config.cfg.base_dir)
        srv = AdminServer(FakeBridge())
        started = await srv.start()
        await srv.stop()
        return started

    assert asyncio.run(go()) is True
    assert config.cfg.admin.host == "127.0.0.1"                      # local by default


# ---------------------------------------------------------------- route test, listen test, device
def test_route_test_validates_its_input_and_listen_test_needs_a_device():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        a = await c.post("/api/route-test", json={"text": ""}, headers=h)
        b = await c.post("/api/route-test", json={"text": "x" * 501}, headers=h)
        d = await c.post("/api/listen-test", headers=h, json={})
        return a.status, b.status, d.status

    assert with_client(run) == (400, 400, 503)


def test_device_controls_over_the_api():
    from types import SimpleNamespace

    from aioesphomeapi import SwitchInfo

    class Client:
        calls: list = []

        def switch_command(self, key, v):
            Client.calls.append((key, v))

    bridge = FakeBridge()
    bridge.client = Client()
    bridge.entities = [SwitchInfo(key=2, object_id="mute", name="Mute")]
    bridge.states = {2: SimpleNamespace(state=False, missing_state=False)}

    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        got = await (await c.get("/api/device")).json()
        ok = await c.post("/api/device", json={"name": "Mute", "value": "on"}, headers=h)
        bad = await c.post("/api/device", json={"name": "Mute", "value": "perhaps"}, headers=h)
        junk = await c.post("/api/device", data="x", headers={**h, "Content-Type": "application/json"})
        return got, ok.status, bad.status, junk.status

    got, ok, bad, junk = with_client(run, bridge=bridge)
    assert got["connected"] and got["controls"][0]["id"] == "mute"
    assert (ok, bad, junk, Client.calls) == (200, 400, 400, [(2, True)])


# ---------------------------------------------------------------- onboarding endpoints
def test_the_brain_check_runs_a_test_call_and_reports_failures():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        good = await (await c.post("/api/check/brain", json={}, headers=h)).json()
        FakeBrain.healthy = False
        try:
            bad = await (await c.post("/api/check/brain", json={}, headers=h)).json()
        finally:
            FakeBrain.healthy = True
        return good, bad

    good, bad = with_client(run)
    assert good["ok"] and good["reply"] == "Hello there, good evening sir." and good["checks"][0]["ok"]
    assert not bad["ok"] and bad["reply"] == "" and bad["checks"][0]["detail"] == "refused"


def test_the_stt_check_compares_what_comes_back():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        good = await (await c.post("/api/check/stt", json={}, headers=h)).json()
        FakeStt.text = "something else entirely"
        try:
            bad = await (await c.post("/api/check/stt", json={}, headers=h)).json()
        finally:
            FakeStt.text = "hello this is a test of speech recognition"
        return good, bad

    good, bad = with_client(run)
    assert good["ok"] and good["providers"][0]["name"] == "fake"
    assert not bad["ok"] and bad["transcript"] == "something else entirely"


def test_doctor_results_are_available_as_json(monkeypatch):
    from hermes_jarvis import doctor

    async def fake_collect(printer=None, running=False):
        assert running is True
        return [("ok", "config file", "x"), ("FAIL", "voice device", "none found")]

    monkeypatch.setattr(doctor, "collect", fake_collect)

    async def run(c, _s):
        await login(c)
        return await (await c.get("/api/doctor")).json()

    assert with_client(run) == [{"level": "ok", "label": "config file", "detail": "x"},
                                {"level": "FAIL", "label": "voice device", "detail": "none found"}]


def test_voices_can_be_listed_previewed_and_selected(monkeypatch):
    bridge = FakeBridge()
    bridge.client = object()

    class P:
        def __init__(self, name):
            self.name = name

        def synth_wav(self, text):
            return b"RIFFwav"

    monkeypatch.setattr(admin_mod, "PiperTTS", P)
    FakeSpeaker.played = []

    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        listing = await (await c.get("/api/voices")).json()
        prev = await c.post("/api/voices/preview", json={"voice": "en_US-ryan-medium"}, headers=h)
        junk = await c.post("/api/voices/preview", json={"voice": "../x"}, headers=h)
        sel = await c.post("/api/voices/select", json={"voice": "en_US-ryan-medium"}, headers=h)
        return listing, prev.status, junk.status, sel.status, await (await c.get("/api/status")).json()

    listing, prev, junk, sel, status = with_client(run, bridge=bridge)
    assert listing["current"] == "en_GB-alan-medium" and any(v["name"] == "en_US-ryan-medium" for v in listing["voices"])
    assert (prev, junk, sel) == (200, 400, 200) and FakeSpeaker.played == ["Good evening. All systems are running normally."]
    assert status["voice"] == "en_US-ryan-medium" and settings.get("tts_voice") == "en_US-ryan-medium"


def test_a_voice_that_cannot_be_loaded_keeps_the_old_one(monkeypatch):
    bridge = FakeBridge()

    async def refuse():
        pass  # apply_voice does nothing, so the tts name stays the old one

    bridge.apply_voice = refuse

    async def run(c, _s):
        csrf = await login(c)
        r = await c.post("/api/voices/select", json={"voice": "en_US-amy-medium"}, headers=headers(c, csrf))
        return r.status

    assert with_client(run, bridge=bridge) == 502 and settings.get("tts_voice") == "en_GB-alan-medium"


def test_discovery_and_adoption(monkeypatch):
    from hermes_jarvis import discovery
    from hermes_jarvis.adopt import AdoptError

    async def fake_discover(timeout=4.0):
        return [discovery.Device("home-assistant-voice-1", "10.0.0.5", 6053, adoptable=True)]

    async def fake_adopt(host, name="", port=6053):
        if host == "10.0.0.9":
            raise AdoptError("already has an encryption key")
        return {"name": "home-assistant-voice-1", "note": "adopted"}

    monkeypatch.setattr(discovery, "discover", fake_discover)
    monkeypatch.setattr(admin_mod.adopt_mod, "adopt", fake_adopt)
    FakeBridge.nudged = 0

    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        found = await (await c.get("/api/discover")).json()
        ok = await c.post("/api/adopt", json={"host": "10.0.0.5"}, headers=h)
        refused = await c.post("/api/adopt", json={"host": "10.0.0.9"}, headers=h)
        evil = [(await c.post("/api/adopt", json={"host": bad}, headers=h)).status
                for bad in ("", "10.0.0.5; rm -rf /", "a b", "x" * 300, "http://x/")]
        return found, ok.status, await ok.json(), refused.status, (await refused.json())["error"], evil

    found, ok, body, refused, msg, evil = with_client(run)
    assert found[0]["host"] == "10.0.0.5" and found[0]["likely_voice"] and found[0]["adoptable"]
    assert ok == 200 and body["name"] == "home-assistant-voice-1" and FakeBridge.nudged == 1
    assert refused == 400 and "encryption key" in msg and evil == [400] * 5


def test_onboarding_completion_is_remembered_in_settings():
    async def run(c, _s):
        csrf = await login(c)
        h = headers(c, csrf)
        await c.put("/api/settings", json={"onboarding_completed": True}, headers=h)
        done = (await (await c.get("/api/status")).json())["onboarding_completed"]
        await c.put("/api/settings", json={"onboarding_completed": False}, headers=h)
        again = (await (await c.get("/api/status")).json())["onboarding_completed"]
        return done, again

    assert with_client(run) == (True, False)
