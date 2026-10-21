"""One spoken turn: transcript -> Hermes -> spoken sentences.

The router (router.py) picks the brain's profile and session: within the session window it keeps the current one,
otherwise a Jev call matches recent session titles and profile descriptions.
"""
import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from . import config, personas, turnlog
from .brains import Brain
from .events import bus
from .router import Router
from .settings import settings
from .speak import SpeakParser
from .speaker import Speaker

log = logging.getLogger("hermes_jarvis.conversation")
STATE_FILE: Path | None = None  # tests and tools may point this elsewhere


def _state_file() -> Path:
    return STATE_FILE or config.cfg.data_path("state.json")


_QUESTION_END = re.compile(r"\?[\s\"')\]]*$")


def is_question(sentence: str, ignore_phrases: list[str] = ()) -> bool:
    """True if the sentence ends with a question mark and is not a closing pleasantry like "anything else?"."""
    s = sentence.strip()
    if not _QUESTION_END.search(s):
        return False
    low = s.lower()
    return not any(p.strip() and p.strip().lower() in low for p in ignore_phrases)


class Conversation:
    def __init__(self, brain: Brain, speaker: Speaker, router: Router):
        self.brain, self.speaker, self.router = brain, speaker, router
        self.session_id: str | None = None
        self.profile = "default"
        self.last_activity = 0.0
        try:
            s = json.loads(_state_file().read_text())
            self.session_id, self.profile, self.last_activity = s["session_id"], s["profile"], s["last_activity"]
        except (OSError, ValueError, KeyError):
            pass

    def _save(self) -> None:
        f = _state_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"session_id": self.session_id, "profile": self.profile, "last_activity": self.last_activity}))
        os.replace(tmp, f)

    def touch(self) -> None:
        """Voice activity (an utterance or a spoken delivery) restarts the session window."""
        self.last_activity = time.time()
        self._save()

    @staticmethod
    def _line(kind: str) -> str:
        """A short fixed line in the active persona ("done", "error"), addressed the way the user asked."""
        return personas.render(personas.get(config.cfg.persona)[kind], settings.get("address_as"))

    def _followup_decision(self, last_spoken: str, utter_ts: float, gen: int) -> int | None:
        if not settings.get("followup_enabled") or not is_question(last_spoken, settings.get("followup_ignore_phrases")):
            return None
        age_min = (time.time() - utter_ts) / 60
        if age_min > float(settings.get("followup_window_minutes")):
            log.info("last sentence is a question but the request was %.1f min ago: not listening", age_min)
            return None
        if gen != self.speaker.generation:
            return None  # the user said stop
        log.info("last sentence is a question: will listen for the answer (%r)", config.shown(last_spoken[-60:]))
        return gen

    async def handle(self, text: str, on_speaking: Callable[[], Awaitable[None]] | None = None) -> int | None:
        """Run one turn. Returns the speaker generation if the device should start listening again (the last thing
        said was a question and the request was recent), otherwise None."""
        t0 = time.monotonic()
        utter_ts = time.time()
        last_spoken = ""
        listen_gen: int | None = None
        parser = SpeakParser()
        gen = self.speaker.generation  # a stop word bumps this and silences the rest of the turn
        spoke = False
        ack_after = float(settings.get("ack_after_s"))
        spoken_chars = 0
        order = asyncio.Lock()  # the ack and the first real sentence must queue in a defined order
        route = None
        first_speech_s = None

        async def speak(sentences: list[str]) -> None:
            nonlocal spoke, first_speech_s
            nonlocal spoken_chars, last_spoken
            for s in sentences:
                spoken_chars += len(s)
                last_spoken = s
                bus.transcript("assistant", s)
                async with order:
                    if not spoke:
                        first_speech_s = round(time.monotonic() - t0, 2)
                        log.info("first speech %.2fs after the transcript: %r", first_speech_s, config.shown(s[:60]))
                        spoke = True
                        if on_speaking:
                            await on_speaking()
                    await self.speaker.say(s, gen)
                    last_voice[0] = time.monotonic()

        async def ack() -> None:
            await asyncio.sleep(ack_after)
            nonlocal spoke, first_speech_s
            async with order:
                if not spoke:
                    line = await self.speaker.say_canned(gen)
                    if line:
                        first_speech_s = round(time.monotonic() - t0, 2)  # the ack is the first thing the user hears
                        log.info("canned ack after %.1fs: %r", ack_after, line)
                        last_voice[0] = time.monotonic()
                        spoke = True
                        if on_speaking:
                            await on_speaking()

        async def progress() -> None:
            """While the brain is silent for a long time (tools running), say a short "still working" line."""
            every = float(settings.get("progress_every_s"))
            if every <= 0:
                return
            lines = personas.get(config.cfg.persona).get("progress") or []
            n = 0
            while lines:
                await asyncio.sleep(every)
                if time.monotonic() - last_voice[0] < every:
                    continue
                async with order:
                    if gen != self.speaker.generation:
                        return
                    text = personas.render(lines[n % len(lines)], settings.get("address_as"))
                    n += 1
                    log.info("progress line after %.0fs of silence: %r", every, text)
                    await self.speaker.say(text, gen)
                    last_voice[0] = time.monotonic()

        last_voice = [time.monotonic()]  # when the user last heard something this turn
        ack_task = asyncio.create_task(ack())  # the ack timer counts from the transcript, routing included
        progress_task = asyncio.create_task(progress())
        try:
            route = await self.router.route(text, self.session_id, self.profile, self.last_activity)
            log.info("route: profile=%s session=%s reason=%s (%d ms)", route.profile,
                     route.session_id or "new", route.reason, route.router_ms)
            bus.route(route.profile, route.reason, route.router_ms, resumed=route.session_id is not None)
            self.session_id, self.profile = route.session_id, route.profile
            self.touch()
            async for ev in self.brain.turn(text, self.session_id, self.profile):
                kind = ev["type"]
                if kind == "session":
                    if ev["id"] != self.session_id:
                        log.info("hermes session %s", ev["id"])
                    self.session_id = ev["id"]
                elif kind == "text":
                    await speak(parser.feed(ev["delta"]))
                elif kind == "tool":
                    bus.tool(ev.get("tool", ""), ev.get("label", ""), ev.get("status", ""))
                    if ev.get("status") == "running":
                        log.info("tool %s: %s", ev.get("tool"), config.shown(str(ev.get("label", ""))[:80]))
                elif kind == "error":
                    await speak([self._line("error")])
                    return None
            await speak(parser.finish())
            if not spoke:
                await speak([self._line("done")])
            listen_gen = self._followup_decision(last_spoken, utter_ts, gen)
        finally:
            ack_task.cancel()
            progress_task.cancel()
            self.touch()
            total = time.monotonic() - t0
            log.info("turn done in %.1fs, session %s", total, self.session_id)
            turnlog.record({"text": text, "profile": self.profile, "session_id": self.session_id,
                            "route": route.as_dict() if route else None, "first_speech_s": first_speech_s,
                            "total_s": round(total, 2), "spoken_chars": spoken_chars,
                            "listen_after": listen_gen is not None})
        return listen_gen
