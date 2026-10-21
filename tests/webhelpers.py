"""Shared pieces for the web UI tests: a fake bridge, a logged-in client, and a tiny exported-app fixture."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from hermes_jarvis import admin as admin_mod
from hermes_jarvis.admin import AdminServer

PASSWORD = "correct horse battery"


class FakeSpeaker:
    prerendered = None
    played: list = []

    async def prerender(self, acks):
        FakeSpeaker.prerendered = acks

    async def start_listening(self):
        return True

    async def play_wav(self, text, wav):
        FakeSpeaker.played.append(text)


class FakeStt:
    name = "fake"
    text = "hello this is a test of speech recognition"

    def check(self):
        return True, "ready"


class FakeSttAll:
    def providers(self):
        return [FakeStt()]

    async def transcribe(self, pcm):
        return FakeStt.text


class FakeTts:
    name = "en_GB-alan-medium"
    sample_rate = 22050

    def synth_pcm(self, text):
        yield b"\0\0" * 2205

    def synth_wav(self, text):
        return b"RIFF" + b"\0" * 100


class FakeBrain:
    name = "hermes"
    supports_profiles = supports_sessions = True
    healthy = True
    reply = "<speak>Hello there, good evening sir.</speak>"

    async def check(self):
        return [("Hermes gateway reachable", FakeBrain.healthy, "ok" if FakeBrain.healthy else "refused")]

    async def turn(self, text, session_id=None, profile="default"):
        yield {"type": "session", "id": "s"}
        yield {"type": "text", "delta": FakeBrain.reply}
        yield {"type": "done"}


class FakeRouter:
    def available(self):
        return False


class FakeConv:
    session_id, profile, last_activity = "api-1", "default", 0.0


class FakeBridge:
    client = None
    active = False
    entities: list = []
    states: dict = {}
    device_name = "voice-1"
    nudged = 0
    voice_applied = 0

    def __init__(self):
        self.brain, self.router, self.speaker, self.conv = FakeBrain(), FakeRouter(), FakeSpeaker(), FakeConv()
        self.tts, self.stt = FakeTts(), FakeSttAll()

    def nudge_reconnect(self):
        FakeBridge.nudged += 1

    async def apply_voice(self):
        from hermes_jarvis.settings import settings
        FakeBridge.voice_applied += 1
        self.tts.name = settings.get("tts_voice")


def origin_of(client: TestClient) -> str:
    return f"http://{client.server.host}:{client.server.port}"


def with_client(fn, bridge=None, server=None):
    """Run `async fn(client, server)` against a fresh admin app."""
    async def go():
        srv = server or AdminServer(bridge or FakeBridge())
        async with TestClient(TestServer(srv.make_app())) as c:
            return await fn(c, srv)
    return asyncio.run(go())


async def login(c: TestClient, password: str = PASSWORD, user: str = "admin") -> str:
    """Sign in and return the CSRF token."""
    r = await c.post("/api/login", json={"username": user, "password": password}, headers={"Origin": origin_of(c)})
    assert r.status == 200, await r.text()
    return (await r.json())["csrf"]


def headers(c: TestClient, csrf: str) -> dict:
    return {"X-CSRF-Token": csrf, "Origin": origin_of(c)}


def fake_app(tmp_path, monkeypatch):
    """A minimal exported Next.js app: a dashboard page and a login page with inline bootstrap scripts."""
    root = tmp_path / "app"
    (root / "login").mkdir(parents=True)
    (root / "_next" / "static").mkdir(parents=True)
    (root / "index.html").write_text("<html><body>dashboard<script>self.__next_f.push([1,\"a\"])</script></body></html>")
    (root / "login" / "index.html").write_text(
        "<html><body>login<script>self.__next_f.push([1,\"b\"])</script><script src=\"/_next/static/x.js\"></script></body></html>")
    (root / "_next" / "static" / "x.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("not for the web")
    monkeypatch.setattr(admin_mod, "APP_DIR", root)
    return root


def fake_settings_ns():
    return SimpleNamespace()
