#!/usr/bin/env python3
"""Run the real web UI with made-up data, a fake device and a scripted stream of live events. No hardware, no keys,
nothing is sent anywhere.

  scripts/admin_demo.py                      open http://127.0.0.1:8680 and sign in with the password "demo"
  scripts/admin_demo.py --autologin          /demo-login signs you in (for screenshots)
  scripts/admin_demo.py --dev                also allow the Next.js dev server (npm run dev, http://localhost:3000)
  scripts/admin_demo.py --fresh              start as a first run, so the setup guide is offered

For UI work: run this in one terminal and `cd webui && npm run dev` in another. The dev server proxies /api to port 8680.
Handy for working on the UI and for taking screenshots for the docs.
"""
import argparse
import asyncio
import os
import random
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from aioesphomeapi import ButtonInfo, SelectInfo, SwitchInfo
from aiohttp import web

from hermes_jarvis import admin as admin_mod
from hermes_jarvis import config, discovery, doctor, turnlog
from hermes_jarvis.admin import AdminServer
from hermes_jarvis.events import bus
from hermes_jarvis.router import Route
from hermes_jarvis.settings import settings

p = argparse.ArgumentParser()
p.add_argument("--port", type=int, default=8680)
p.add_argument("--autologin", action="store_true", help="GET /demo-login signs in without typing the password")
p.add_argument("--dev", action="store_true", help="allow the Next.js dev server origin (http://localhost:3000)")
p.add_argument("--fresh", action="store_true", help="start as a first run: the setup guide has not been completed")
args = p.parse_args()

PORT = args.port
tmp = Path(tempfile.mkdtemp(prefix="hermes-jarvis-demo-"))
origins = ["http://localhost:3000", "http://127.0.0.1:3000"] if args.dev else []
config.use({"data_dir": str(tmp / "data"), "persona": "jarvis",
            "admin": {"port": PORT, "allowed_origins": origins}}, base_dir=tmp)
for key in ("ADMIN_PASSWORD", "HERMES_API_KEY", "HERMES_API_KEY_WORK", "OPENROUTER_API_KEY", "ELEVENLABS_API_KEY"):
    os.environ[key] = "demo"

settings.update({"profiles": [
    {"name": "default", "is_default": True, "enabled": True,
     "description": "General requests, home, health, travel, and anything that does not clearly belong elsewhere."},
    {"name": "work", "is_default": False, "enabled": True,
     "description": "Clients, invoices, contracts, project work and meetings for my company."},
    {"name": "home", "is_default": False, "enabled": False,
     "description": "Family, shopping lists, the house, and plans for the weekend."},
]})
settings.update({"piper_length_scale": 1.1, "ack_after_s": 2.0, "onboarding_completed": not args.fresh})

now = time.time()
for ago, text, profile, reason, router_ms, first, total, chars in [
    (40, "What's on my calendar this afternoon?", "default", "window", 0, 1.9, 6.1, 210),
    (95, "And move the dentist to Thursday", "default", "window", 0, 1.4, 4.8, 120),
    (900, "What's the status of the October invoice for the Acme project?", "work", "jev-resume", 248, 2.5, 9.7, 360),
    (2400, "Remind me to call my sister tomorrow evening", "default", "jev-new", 231, 1.8, 5.2, 95),
    (5200, "Summarize the unread emails from the client", "work", "jev-new", 266, 2.5, 21.3, 540),
]:
    turnlog.record({"ts": now - ago, "text": text, "profile": profile, "session_id": "api-demo",
                    "route": {"reason": reason, "router_ms": router_ms}, "first_speech_s": first,
                    "total_s": total, "spoken_chars": chars, "listen_after": False})


# ---------------------------------------------------------------- fakes for the pieces that need hardware
class FakeRouter:
    def available(self):
        return True

    async def route(self, text, sid, profile, last, ignore_window=False):
        cands = [{"id": "api-inv", "profile": "work", "title": "October invoice status, Acme project", "age_min": 15},
                 {"id": "api-cal", "profile": "default", "title": "Calendar and dentist appointment", "age_min": 1},
                 {"id": "api-sis", "profile": "default", "title": "Reminder to call sister", "age_min": 40}]
        return Route("work", "api-inv", "jev-resume", {"default": 0.03, "work": 0.97, "home": 0.0},
                     {"new": 0.02, "api-inv": 0.96, "api-cal": 0.01, "api-sis": 0.01}, cands, 252)


class FakeBrain:
    name = "hermes"
    supports_profiles = supports_sessions = True

    async def check(self):
        await asyncio.sleep(0.4)
        return [("Hermes gateway reachable", True, "http://hermes.local:8642/health -> HTTP 200"),
                ("Hermes profile 'default' key", True, "accepted"),
                ("Hermes profile 'work' key", True, "accepted")]

    async def turn(self, text, session_id=None, profile="default"):
        await asyncio.sleep(0.8)
        yield {"type": "session", "id": "demo"}
        yield {"type": "text", "delta": "<speak>Good evening, sir. Systems are online.</speak>"}
        yield {"type": "done"}


class FakeStt:
    name = "elevenlabs"

    def check(self):
        return True, "key set"


class FakeSttSet:
    def providers(self):
        return [FakeStt()]

    async def transcribe(self, pcm):
        await asyncio.sleep(0.5)
        return "Hello. This is a test of speech recognition."


class FakeTts:
    name = "en_GB-alan-medium"
    sample_rate = 22050

    def synth_pcm(self, text):
        yield b"\0\0" * 2205


class FakeSpeaker:
    async def prerender(self, *_):
        return None

    async def start_listening(self):
        bus.set_state("followup")
        asyncio.get_running_loop().call_later(5, lambda: bus.set_state("idle"))
        return True

    async def play_wav(self, text, wav):
        bus.set_state("speaking")
        asyncio.get_running_loop().call_later(2.5, lambda: bus.set_state("idle"))


ENTS = [SelectInfo(key=1, object_id="wake_word_sensitivity", name="Wake word sensitivity",
                   options=["Slightly sensitive", "Moderately sensitive", "Very sensitive"]),
        SwitchInfo(key=2, object_id="mute", name="Mute"),
        SwitchInfo(key=3, object_id="wake_sound", name="Wake sound"),
        ButtonInfo(key=4, object_id="restart", name="Restart")]
STATES = {1: SimpleNamespace(state="Slightly sensitive", missing_state=False),
          2: SimpleNamespace(state=False, missing_state=False), 3: SimpleNamespace(state=True, missing_state=False)}


class FakeClient:
    def select_command(self, key, value):
        STATES[key] = SimpleNamespace(state=value, missing_state=False)

    def switch_command(self, key, value):
        STATES[key] = SimpleNamespace(state=value, missing_state=False)

    def button_command(self, key):
        pass

    def number_command(self, key, value):
        pass


class FakeBridge:
    client, active = FakeClient(), False
    device_name = "hermes-jarvis-a1b2c3"
    entities, states = ENTS, STATES
    brain, router, speaker = FakeBrain(), FakeRouter(), FakeSpeaker()
    tts, stt = FakeTts(), FakeSttSet()
    conv = SimpleNamespace(session_id="api-cal", profile="default", last_activity=now - 40)

    def nudge_reconnect(self):
        pass

    async def apply_voice(self):
        self.tts.name = settings.get("tts_voice")


async def fake_discover(timeout=4.0):
    await asyncio.sleep(1.0)
    return [discovery.Device("hermes-jarvis-a1b2c3", "192.168.1.50", 6053, "AA:BB:CC", "2025.7.2",
                             "Nabu Casa.Home Assistant Voice PE", adopted=False, adoptable=True),
            discovery.Device("kitchen-plug", "192.168.1.61", 6053, version="2025.7.2")]


async def fake_adopt(host, name="", port=6053):
    await asyncio.sleep(1.2)
    return {"name": "hermes-jarvis-a1b2c3", "note": "adopted"}


async def fake_doctor(printer=None, running=False):
    return [("ok", "config file", "config.yaml"), ("ok", "data directory writable", "/data"),
            ("ok", "Hermes gateway reachable", "http://hermes.local:8642/health -> HTTP 200"),
            ("ok", "speech to text (elevenlabs)", "key set"), ("ok", "speech voice", "en_GB-alan-medium installed"),
            ("ok", "device connection", "hermes-jarvis-a1b2c3, ESPHome 2025.7.2"),
            ("warn", "router", "optional: OPENROUTER_API_KEY is set"), ("ok", "stop word support", "present")]


discovery.discover = fake_discover
admin_mod.adopt_mod.adopt = fake_adopt
doctor.collect = fake_doctor


# ---------------------------------------------------------------- scripted live events
async def conversation_loop() -> None:
    """Replays a believable exchange forever so the core, the feed and the readouts have something to show."""
    bus.set_device(True, FakeBridge.device_name)
    script = [
        ("What's the status of the October invoice for the Acme project?",
         "Checking the finance folder.", "search_files", "finance/acme/2026-10",
         ["The October invoice was sent on the ninth and is still unpaid.", "It is due on the twenty-third."], True),
        ("Remind me to call my sister tomorrow evening.", None, None, None,
         ["Done. I will remind you tomorrow at six."], False),
    ]
    i = 0
    while True:
        q, pre, tool, label, answer, follow = script[i % len(script)]
        i += 1
        await asyncio.sleep(5)
        bus.set_state("wake")
        await asyncio.sleep(0.7)
        for _ in range(8):  # listening: quiet room
            bus.level(random.uniform(0.02, 0.06))
            await asyncio.sleep(0.11)
        bus.set_state("speech")
        end = time.monotonic() + 2.6
        while time.monotonic() < end:
            bus.level(random.uniform(0.25, 0.95))
            await asyncio.sleep(0.1)
        bus.set_state("thinking")
        bus.transcript("user", q)
        await asyncio.sleep(0.5)
        bus.route("work" if tool else "default", "jev-resume" if tool else "window", 252 if tool else 0, True)
        await asyncio.sleep(1.8)
        bus.transcript("assistant", "One moment, sir.")
        bus.set_state("speaking")
        await asyncio.sleep(1.5)
        if pre:
            bus.transcript("assistant", pre)
            bus.tool(tool, label, "running")
            await asyncio.sleep(2.2)
            bus.tool(tool, label, "completed")
        bus.set_state("thinking")
        await asyncio.sleep(1.2)
        bus.set_state("speaking")
        for line in answer:
            bus.transcript("assistant", line)
            await asyncio.sleep(3.0)
        if follow:
            bus.transcript("assistant", "Shall I draft a reminder to them?")
            await asyncio.sleep(2.2)
            bus.set_state("followup")
            await asyncio.sleep(5.5)
        bus.set_state("idle")


class DemoAdmin(AdminServer):
    """Adds /demo-login (with --autologin): signs in without the password. Demo only; the real server has no such route."""

    def make_app(self) -> web.Application:
        app = super().make_app()

        async def start_events(_app):
            _app["events"] = asyncio.create_task(conversation_loop())
        app.on_startup.append(start_events)
        return app

    async def static(self, request: web.Request) -> web.StreamResponse:
        if args.autologin and request.path == "/demo-login":
            sid, _ = self.auth.create("demo")
            resp = web.HTTPFound("/")
            resp.set_cookie(self._cookie_name(request), sid, httponly=True, samesite="Strict", path="/")
            raise resp
        return await super().static(request)


PUBLIC = admin_mod.PUBLIC_PATHS
if args.autologin:
    PUBLIC.add("/demo-login")

print(f"demo UI on http://127.0.0.1:{PORT}  (password: demo{'; autologin at /demo-login' if args.autologin else ''}; data in {tmp})")
web.run_app(DemoAdmin(FakeBridge()).make_app(), host="127.0.0.1", port=PORT, print=None)
