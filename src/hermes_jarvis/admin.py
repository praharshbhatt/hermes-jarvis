"""The web UI server: serves the exported Next.js app and its JSON API, behind a real login.

Safe defaults: it is off unless ADMIN_PASSWORD (or ADMIN_PASSWORD_HASH) is set, and it listens on 127.0.0.1 unless
admin.host says otherwise. Sign-in creates a server-side session (HttpOnly, SameSite=Strict cookie, Secure over https);
state-changing requests need the session's CSRF token and a same-origin Origin; responses carry strict security headers
and a Content-Security-Policy with no inline-script allowance beyond the hashes of the exported pages' own scripts.
It is plain HTTP unless you put TLS in front of it: use a reverse proxy, or a VPN such as Tailscale, beyond one machine.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import re
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from aiohttp import web

from . import adopt as adopt_mod
from . import auth, config, devicectl, discovery, doctor, turnlog
from .events import bus
from .settings import settings
from .speak import SpeakParser
from .tts import PiperTTS, voices

log = logging.getLogger("hermes_jarvis.admin")
APP_DIR = Path(__file__).parent / "static" / "app"   # the exported web UI (see scripts/build_ui.sh)

MAX_BODY = 256 * 1024
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
PUBLIC_PATHS = {"/healthz", "/api/session", "/api/login", "/login/", "/icon.svg", "/favicon.ico", "/robots.txt"}
PUBLIC_PREFIXES = ("/_next/",)   # built JS, CSS and fonts: nothing private in them
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
SAMPLE_LINE = "Good evening. All systems are running normally."

# typed keys for per-request data (plain string keys are deprecated in aiohttp)
K_SESSION = web.RequestKey("session", object)
K_SID = web.RequestKey("sid", object)
K_CSP = web.RequestKey("csp", str)


def _stt_key_names() -> list[str]:
    c = config.cfg.stt
    names = {"elevenlabs": "ELEVENLABS_API_KEY", "deepgram": "DEEPGRAM_API_KEY", "openai": "OPENAI_API_KEY"}
    return [names[p] for p in (c.provider, c.compare_with) if p in names]


def _json(data, status: int = 200, **kw) -> web.Response:
    return web.json_response(data, status=status, **kw)


def _err(message: str, status: int = 400) -> web.Response:
    return _json({"error": message}, status)


class AdminServer:
    def __init__(self, bridge) -> None:
        self.bridge = bridge
        self.started = time.time()
        self.auth = auth.AuthManager()
        self._runner: web.AppRunner | None = None
        self._voice_lock = asyncio.Lock()
        self._html_cache: dict[Path, tuple[float, bytes, str]] = {}

    # ================= request helpers =================
    @staticmethod
    def _secure(request: web.Request) -> bool:
        if request.secure:
            return True
        return bool(config.cfg.admin.trust_proxy) and request.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _cookie_name(self, request: web.Request) -> str:
        return auth.COOKIE_SECURE if self._secure(request) else auth.COOKIE

    def _origin_ok(self, request: web.Request) -> bool:
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        origin = request.headers.get("Origin")
        if origin is None:
            return True  # not a browser page (curl, a script): the CSRF token still has to match
        scheme = "https" if self._secure(request) else "http"
        return origin in {f"{scheme}://{request.host}", *config.cfg.admin.allowed_origins}

    @staticmethod
    async def _body(r: web.Request) -> dict:
        if r.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text=json.dumps({"error": "send application/json"}),
                                               content_type="application/json")
        try:
            body = await r.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text=json.dumps({"error": "expected a JSON object"}), content_type="application/json")
        return body

    # ================= middleware and headers =================
    @web.middleware
    async def _guard(self, request: web.Request, handler):
        path = request.path
        sid = request.cookies.get(self._cookie_name(request))
        background = request.headers.get("X-HJ-Background") == "1"  # polling must not keep a session alive
        session = self.auth.get(sid, touch=not background and path != "/api/events")
        request[K_SESSION], request[K_SID] = session, sid
        public = path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)

        if not public and session is None:
            if path.startswith("/api/"):
                return _err("login required", 401)
            raise web.HTTPFound("/login/")
        if path == "/login/" and session is not None:
            raise web.HTTPFound("/")
        if request.method not in SAFE_METHODS:
            if not self._origin_ok(request):
                return _err("cross-origin request refused", 403)
            if path != "/api/login":
                if session is None or not auth.csrf_ok(session, request.headers.get("X-CSRF-Token")):
                    return _err("missing or wrong CSRF token", 403)
        return await handler(request)

    async def _on_prepare(self, request: web.Request, response: web.StreamResponse) -> None:
        """Runs just before headers go out, so it covers streams and error pages too."""
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        h["Content-Security-Policy"] = request.get(K_CSP) or "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        if request.path.startswith("/_next/static/"):
            h.setdefault("Cache-Control", "public, max-age=31536000, immutable")  # content-hashed file names
        else:
            h.setdefault("Cache-Control", "no-store")
        if self._secure(request):
            h["Strict-Transport-Security"] = "max-age=31536000"

    # ================= login and session =================
    async def session_info(self, request: web.Request) -> web.Response:
        s = request[K_SESSION]
        base = {"authenticated": s is not None, "user": config.cfg.admin.user}
        if s is not None:
            base.update(csrf=s.csrf, idle_seconds=int(self.auth.idle_seconds()),
                        expires_in=int(max(0, s.created + self.auth.max_seconds() - time.time())))
        return _json(base)

    async def login(self, request: web.Request) -> web.Response:
        who = request.remote or "?"
        if self.auth.locked_out(who):
            return _json({"error": "too many failed logins; try again in a few minutes"}, 429,
                         headers={"Retry-After": str(int(self.auth.LOCKOUT_WINDOW))})
        body = await self._body(request)
        user, password = str(body.get("username", ""))[:200], str(body.get("password", ""))[:500]
        if not auth.check_login(user, password):
            self.auth.record_failure(who)
            await asyncio.sleep(0.5)  # slow down guessing
            return _err("wrong username or password", 401)
        self.auth.clear_failures(who)
        self.auth.destroy(request.get(K_SID))  # a fresh id on every login (no session fixation)
        sid, s = self.auth.create(who)
        resp = _json({"authenticated": True, "csrf": s.csrf, "user": config.cfg.admin.user})
        resp.set_cookie(self._cookie_name(request), sid, httponly=True, secure=self._secure(request),
                        samesite="Strict", path="/", max_age=int(self.auth.max_seconds()))
        log.info("admin login from %s", who)
        return resp

    async def logout(self, request: web.Request) -> web.Response:
        self.auth.destroy(request.get(K_SID))
        resp = _json({"ok": True})
        resp.del_cookie(self._cookie_name(request), path="/")
        return resp

    # ================= status, settings, history =================
    def _secret_status(self) -> dict:
        c = config.cfg
        keys: list[str] = []
        if c.brain.api_key_env:
            keys.append(c.brain.api_key_env)
        if self.bridge.brain.supports_profiles:
            for p in settings.get("profiles"):
                if p["is_default"] or not p["enabled"]:
                    continue
                keys.append(f"{c.brain.api_key_env}_{p['name'].upper()}")
        keys += _stt_key_names()
        if self.bridge.router.available() or settings.get("router_enabled"):
            keys.append("OPENROUTER_API_KEY")
        return {k: bool(config.secret(k)) for k in dict.fromkeys(keys)}

    async def healthz(self, _r: web.Request) -> web.Response:
        return _json({"ok": True, "device_connected": self.bridge.client is not None})

    async def status(self, _r: web.Request) -> web.Response:
        b = self.bridge
        c = b.conv
        return _json({
            "device_connected": b.client is not None,
            "device_name": getattr(b, "device_name", ""),
            "uptime_s": int(time.time() - self.started),
            "state": bus.state,
            "session_id": c.session_id, "profile": c.profile,
            "minutes_since_voice_activity": round((time.time() - c.last_activity) / 60, 1) if c.last_activity else None,
            "brain": {"name": b.brain.name, "profiles": b.brain.supports_profiles, "sessions": b.brain.supports_sessions},
            "router_available": b.router.available(),
            "persona": config.cfg.persona,
            "stt": config.cfg.stt.provider,
            "voice": settings.get("tts_voice"),
            "onboarding_completed": bool(settings.get("onboarding_completed")),
            "secrets": self._secret_status(),
            "profile_keys": {p["name"]: bool(config.secret(
                config.cfg.brain.api_key_env if p["is_default"] else f"{config.cfg.brain.api_key_env}_{p['name'].upper()}"))
                for p in settings.get("profiles")},
        })

    async def get_settings(self, _r: web.Request) -> web.Response:
        return _json(settings.all())

    @staticmethod
    def _voice_valid(name) -> bool:
        if not isinstance(name, str) or not name or len(name) > 300:
            return False
        return name in voices.CATALOG or (name.endswith(".onnx") and Path(name).expanduser().is_file())

    async def put_settings(self, r: web.Request) -> web.Response:
        body = await self._body(r)
        if "tts_voice" in body and not self._voice_valid(body["tts_voice"]):
            return _err("tts_voice: not a known voice (see Voices in the UI) or a missing .onnx file")
        try:
            changed = settings.update(body)
        except (ValueError, KeyError, TypeError) as e:
            return _err(str(e))
        if "tts_voice" in changed:
            asyncio.create_task(self.bridge.apply_voice())
        elif {"canned_acks", "address_as", "piper_length_scale", "piper_noise_scale", "piper_noise_w_scale"} & set(changed):
            asyncio.create_task(self.bridge.speaker.prerender(settings.acks()))  # acks use the new wording and voice
        log.info("settings changed: %s", changed)
        return _json({"changed": changed})

    async def history(self, _r: web.Request) -> web.Response:
        return _json(settings.history())

    async def turns(self, _r: web.Request) -> web.Response:
        return _json(turnlog.recent(40))

    async def route_test(self, r: web.Request) -> web.Response:
        body = await self._body(r)
        text = str(body.get("text", "")).strip()
        if not text or len(text) > 500:
            return _err("text is required (up to 500 characters)")
        c = self.bridge.conv
        route = await self.bridge.router.route(text, c.session_id, c.profile, c.last_activity,
                                               ignore_window=bool(body.get("ignore_window", True)))
        return _json(route.as_dict())

    async def listen_test(self, _r: web.Request) -> web.Response:
        """Make the device start listening now (no wake word), as it does after a question."""
        b = self.bridge
        if b.client is None:
            return _err("device not connected", 503)
        if b.active:
            return _err("a voice session is already running", 409)
        return _json({"ok": await b.speaker.start_listening()})

    # ================= the device =================
    async def device_get(self, _r: web.Request) -> web.Response:
        b = self.bridge
        return _json({"connected": b.client is not None,
                      "controls": devicectl.describe(b.entities, b.states) if b.client else []})

    async def device_set(self, r: web.Request) -> web.Response:
        b = self.bridge
        body = await self._body(r)  # validate the request first, then look at the device
        if b.client is None:
            return _err("device not connected", 503)
        try:
            msg = devicectl.apply(b.client, b.entities, str(body.get("name", ""))[:100], body.get("value"))
        except (ValueError, TypeError) as e:
            return _err(str(e))
        log.info("device: %s", msg)
        return _json({"ok": msg})

    # ================= live events (server-sent events) =================
    async def events(self, request: web.Request) -> web.StreamResponse:
        s = request[K_SESSION]
        if s.streams >= 4:
            return _err("too many open live views", 429)
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store",
                                           "X-Accel-Buffering": "no", "Connection": "keep-alive"})
        await resp.prepare(request)
        q = bus.subscribe()
        s.streams += 1
        try:
            await resp.write(b"retry: 3000\n\n" + self._sse("snapshot", bus.snapshot()))
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), 15)
                    await resp.write(self._sse(event["type"], event))
                except TimeoutError:
                    if self.auth.get(request[K_SID], touch=False) is None:  # signed out or expired: end the stream
                        await resp.write(self._sse("end", {"reason": "session ended"}))
                        break
                    await resp.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            bus.unsubscribe(q)
            s.streams = max(0, s.streams - 1)
        return resp

    @staticmethod
    def _sse(name: str, data: dict) -> bytes:
        return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()

    # ================= onboarding: checks the first-run guide uses =================
    async def doctor_run(self, _r: web.Request) -> web.Response:
        rows = await doctor.collect(running=True)
        return _json([{"level": lv, "label": lb, "detail": dt} for lv, lb, dt in rows])

    async def check_brain(self, _r: web.Request) -> web.Response:
        """Ask the brain for five words: proves the URL, the key and the model, and shows how it sounds."""
        brain = self.bridge.brain
        checks = [{"label": lb, "ok": ok, "detail": dt} for lb, ok, dt in await brain.check()]
        reply, error, t0 = "", "", time.monotonic()
        if all(c["ok"] for c in checks):
            parser = SpeakParser()
            try:
                async with asyncio.timeout(60):
                    async for ev in brain.turn("Reply with exactly five words, as a short greeting.", None, "default"):
                        if ev["type"] == "text":
                            reply += " ".join(parser.feed(ev["delta"])) + " "
                        elif ev["type"] == "error":
                            error = f"HTTP {ev.get('status')}: {ev.get('detail', '')[:160]}"
                            break
                reply = (reply + " ".join(parser.finish())).strip()
            except TimeoutError:
                error = "no answer within 60 seconds"
        return _json({"ok": all(c["ok"] for c in checks) and not error and bool(reply), "checks": checks,
                      "reply": reply, "error": error, "seconds": round(time.monotonic() - t0, 2)})

    async def check_stt(self, _r: web.Request) -> web.Response:
        """Speak a sentence with the current voice, feed it to speech to text, and compare what comes back."""
        b = self.bridge
        providers = []
        for p in b.stt.providers():
            ok, detail = p.check()
            providers.append({"name": p.name, "ok": ok, "detail": detail})
        phrase = "Hello. This is a test of speech recognition."
        transcript, t0 = "", time.monotonic()
        if all(p["ok"] for p in providers):
            chunks = await asyncio.to_thread(lambda: list(b.tts.synth_pcm(phrase)))
            pcm22 = np.frombuffer(b"".join(chunks), dtype=np.int16)
            n = int(len(pcm22) * 16000 / b.tts.sample_rate)
            pcm16 = np.interp(np.linspace(0, len(pcm22) - 1, n), np.arange(len(pcm22)), pcm22.astype(np.float32))
            transcript = await b.stt.transcribe(pcm16.astype(np.int16).tobytes())
        words = set(re.findall(r"[a-z]+", transcript.lower()))
        matched = len(words & {"hello", "this", "is", "a", "test", "of", "speech", "recognition"}) >= 5
        return _json({"ok": matched, "providers": providers, "transcript": transcript,
                      "seconds": round(time.monotonic() - t0, 2)})

    async def voices_list(self, _r: web.Request) -> web.Response:
        current = settings.get("tts_voice")
        return _json({"current": current, "voices": [
            {"name": n, "description": d, "installed": voices.installed(n), "current": n == current}
            for n, (_, d) in voices.CATALOG.items()]})

    async def voice_preview(self, r: web.Request) -> web.Response:
        body = await self._body(r)
        name = body.get("voice")
        if not self._voice_valid(name):
            return _err("unknown voice")
        b = self.bridge
        if b.client is None:
            return _err("device not connected", 503)
        async with self._voice_lock:
            try:
                def build() -> bytes:
                    tts = b.tts if name == b.tts.name else PiperTTS(name)  # downloads the voice first if needed
                    return tts.synth_wav(SAMPLE_LINE)
                wav = await asyncio.to_thread(build)
            except Exception as e:
                log.warning("voice preview failed: %s", e)
                return _err(f"could not load that voice: {e}", 502)
        await b.speaker.play_wav(SAMPLE_LINE, wav)
        return _json({"ok": True})

    async def voice_select(self, r: web.Request) -> web.Response:
        body = await self._body(r)
        name = body.get("voice")
        if not self._voice_valid(name):
            return _err("unknown voice")
        old = settings.get("tts_voice")
        async with self._voice_lock:
            settings.update({"tts_voice": name})
            await self.bridge.apply_voice()
            if self.bridge.tts.name != name:  # it did not load: put the old setting back
                settings.update({"tts_voice": old})
                return _err("that voice could not be loaded; the previous one is kept", 502)
        return _json({"ok": True, "voice": name})

    async def discover(self, _r: web.Request) -> web.Response:
        found = await discovery.discover(timeout=4.0)
        return _json([{**asdict(d), "likely_voice": d.likely_voice} for d in found])

    async def adopt(self, r: web.Request) -> web.Response:
        body = await self._body(r)
        host = str(body.get("host", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}", host):
            return _err("host must be an IP address or hostname")
        try:
            out = await adopt_mod.adopt(host, str(body.get("name", ""))[:100], int(config.cfg.device.port))
        except adopt_mod.AdoptError as e:
            return _err(str(e))
        self.bridge.nudge_reconnect()
        return _json({"ok": True, "name": out["name"], "host": host, "note": out["note"]})

    # ================= the web app (static files) =================
    def _html(self, path: Path) -> tuple[bytes, str]:
        """An exported page and its Content-Security-Policy: scripts only from this site, plus the hashes of that
        page's own inline bootstrap scripts (so no 'unsafe-inline' is needed)."""
        mtime = path.stat().st_mtime
        cached = self._html_cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1], cached[2]
        raw = path.read_bytes()
        hashes = {base64.b64encode(hashlib.sha256(m.encode()).digest()).decode()
                  for m in INLINE_SCRIPT.findall(raw.decode("utf-8", "replace")) if m.strip()}
        script = " ".join(["'self'"] + [f"'sha256-{h}'" for h in sorted(hashes)])
        csp = ("default-src 'none'; "
               f"script-src {script}; style-src 'self'; style-src-attr 'unsafe-inline'; "
               "img-src 'self' data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; "
               "form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'")
        self._html_cache[path] = (mtime, raw, csp)
        return raw, csp

    async def static(self, request: web.Request) -> web.StreamResponse:
        root = APP_DIR.resolve()
        if not root.is_dir():
            return web.Response(status=503, content_type="text/plain",
                                text="The web UI is not built. Run scripts/build_ui.sh (needs Node 20+), or install a release.")
        rel = request.path.lstrip("/")
        names = ["index.html"] if not rel else [rel, rel.rstrip("/") + "/index.html", rel.rstrip("/") + ".html"]
        for name in names:
            try:
                p = (root / name).resolve()
                p.relative_to(root)  # a path that climbs out of the app folder raises
            except (ValueError, OSError):
                continue
            if p.is_file():
                if p.suffix == ".html":
                    body, csp = self._html(p)
                    request[K_CSP] = csp
                    return web.Response(body=body, content_type="text/html", charset="utf-8")
                ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                return web.Response(body=p.read_bytes(), content_type=ctype.split(";")[0])
        return web.Response(status=404, text="not found", content_type="text/plain")

    # ================= app and lifecycle =================
    def make_app(self) -> web.Application:
        app = web.Application(middlewares=[self._guard], client_max_size=MAX_BODY)
        app.on_response_prepare.append(self._on_prepare)
        app.add_routes([
            web.get("/healthz", self.healthz),
            web.get("/api/session", self.session_info), web.post("/api/login", self.login),
            web.post("/api/logout", self.logout),
            web.get("/api/status", self.status),
            web.get("/api/settings", self.get_settings), web.put("/api/settings", self.put_settings),
            web.get("/api/history", self.history), web.get("/api/turns", self.turns),
            web.post("/api/route-test", self.route_test), web.post("/api/listen-test", self.listen_test),
            web.get("/api/device", self.device_get), web.post("/api/device", self.device_set),
            web.get("/api/events", self.events),
            web.get("/api/doctor", self.doctor_run),
            web.post("/api/check/brain", self.check_brain), web.post("/api/check/stt", self.check_stt),
            web.get("/api/voices", self.voices_list), web.post("/api/voices/preview", self.voice_preview),
            web.post("/api/voices/select", self.voice_select),
            web.get("/api/discover", self.discover), web.post("/api/adopt", self.adopt),
            web.get("/{tail:.*}", self.static),
        ])
        return app

    async def start(self) -> bool:
        """Start the server. Returns False (and logs why) when it is off for lack of a password."""
        if not auth.credentials_configured():
            log.warning("the web UI is off: set ADMIN_PASSWORD (or ADMIN_PASSWORD_HASH) in .env or the environment to enable it")
            return False
        self._runner = web.AppRunner(self.make_app())
        await self._runner.setup()
        host, port = config.cfg.admin.host, int(config.cfg.admin.port)
        await web.TCPSite(self._runner, host, port).start()
        log.info("web UI on http://%s:%d (user %s)", host, port, config.cfg.admin.user)
        if host not in ("127.0.0.1", "localhost", "::1"):
            log.warning("the web UI is listening beyond localhost over plain HTTP: keep it on a trusted network or behind TLS")
        return True

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
