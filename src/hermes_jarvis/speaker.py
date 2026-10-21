"""Plays sentence clips on the device one after another through its media player (announcement).

Each clip is a WAV the device fetches from the bridge. The queue sends the next clip when the media player
reports idle, so a long pause from Hermes (tool calls) never leaves a half-open audio stream.
"""
import asyncio
import io
import logging
import random
import time
import wave
from collections.abc import Callable

from aioesphomeapi import APIClient, APIConnectionError, MediaPlayerCommand, MediaPlayerState

from . import config
from .audio_server import AudioServer
from .events import bus
from .tts import PiperTTS

log = logging.getLogger("hermes_jarvis.speaker")

BUSY = (MediaPlayerState.PLAYING, MediaPlayerState.ANNOUNCING)


def wav_seconds(wav: bytes, rate: int) -> float:
    return max(0.0, (len(wav) - 44) / (rate * 2))


class Speaker:
    def __init__(self, tts: PiperTTS, audio: AudioServer,
                 get_client: Callable[[], APIClient | None], get_media_key: Callable[[], int | None]):
        self.tts, self.audio = tts, audio
        self._get_client, self._get_key = get_client, get_media_key
        self._q: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._state = MediaPlayerState.IDLE
        self._changed = asyncio.Event()
        self._worker: asyncio.Task | None = None
        self.canned: list[tuple[str, bytes]] = []
        self._last_canned = ""
        self.speaking = False  # a clip is queued or playing
        self.generation = 0    # bumped by cancel(); a turn that started earlier stops being spoken
        buf = io.BytesIO()     # 0.15 s of silence: the "media" played right before the device starts listening
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tts.sample_rate)
            w.writeframes(b"\0" * int(tts.sample_rate * 0.15) * 2)
        self._silence = buf.getvalue()

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def on_media_state(self, state: MediaPlayerState) -> None:
        self._state = state
        self._changed.set()

    async def prerender(self, texts: list[str]) -> None:
        self.canned = [(t, await asyncio.to_thread(self.tts.synth_wav, t)) for t in texts]

    async def drain(self, timeout: float = 600.0) -> None:
        """Wait until everything queued has been played."""
        end = time.monotonic() + timeout
        while self.speaking and time.monotonic() < end:
            await asyncio.sleep(0.2)

    async def start_listening(self) -> bool:
        """Make the device start a voice session now, with no wake word (it plays a short silent clip first)."""
        client = self._get_client()
        if client is None:
            return False
        url = self.audio.add_wav(self._silence)
        try:
            res = await client.send_voice_assistant_announcement_await_response(
                url, timeout=8.0, text="", start_conversation=True)
        except (TimeoutError, APIConnectionError) as e:
            log.warning("start_conversation failed: %s", e)
            return False
        log.info("device told to listen (announce finished, success=%s)", res.success)
        return bool(res.success)

    def cancel(self) -> None:
        """The user said stop: drop everything queued and ignore the rest of the turns already running."""
        self.generation += 1
        bus.set_state("stopped")
        try:
            asyncio.get_running_loop().call_later(1.2, lambda: bus.set_state("idle") if bus.state == "stopped" else None)
        except RuntimeError:  # no running loop (called from a plain test)
            pass
        dropped = 0
        while not self._q.empty():
            self._q.get_nowait()
            dropped += 1
        self.speaking = False
        self._stop_playing()
        log.info("stop: dropped %d queued clip(s), generation now %d", dropped, self.generation)

    def _stop_playing(self) -> None:
        """Cut off the clip already handed to the device. A clip requested a moment before the stop word may not be
        playing yet, so the stop is repeated once shortly after."""
        client, key = self._get_client(), self._get_key()
        if client is None or key is None:
            return

        def stop_now() -> None:
            try:
                client.media_player_command(key, command=MediaPlayerCommand.STOP, announcement=True)
            except Exception as e:
                log.debug("could not stop the playing clip: %s", e)
        stop_now()
        try:
            asyncio.get_running_loop().call_later(
                0.4, lambda: stop_now() if self._state in BUSY else None)
        except RuntimeError:
            pass

    async def say(self, text: str, generation: int | None = None) -> None:
        if generation is not None and generation != self.generation:
            return
        t0 = time.monotonic()
        wav = await asyncio.to_thread(self.tts.synth_wav, text)
        log.info("tts %.2fs for %d chars", time.monotonic() - t0, len(text))
        if generation is not None and generation != self.generation:
            return  # stop was said while this was being synthesized
        self.speaking = True
        await self._q.put((text, wav))

    async def play_wav(self, text: str, wav: bytes) -> None:
        """Queue a prepared clip (a voice preview)."""
        self.speaking = True
        await self._q.put((text, wav))

    async def say_canned(self, generation: int | None = None) -> str | None:
        if not self.canned or (generation is not None and generation != self.generation):
            return None
        # never the same line twice in a row
        choices = [c for c in self.canned if c[0] != self._last_canned] or self.canned
        text, wav = random.choice(choices)
        self._last_canned = text
        self.speaking = True
        await self._q.put((text, wav))
        return text

    async def _run(self) -> None:
        while True:
            text, wav = await self._q.get()
            try:
                await self._play(text, wav, self.generation)
            except Exception:
                log.exception("playback failed")
            self.speaking = not self._q.empty()
            if not self.speaking and bus.state == "speaking":
                bus.set_state("idle")

    async def _wait_state(self, want_busy: bool, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while (self._state in BUSY) != want_busy:
            left = end - time.monotonic()
            if left <= 0:
                return False
            self._changed.clear()
            try:
                await asyncio.wait_for(self._changed.wait(), left)
            except TimeoutError:
                return False
        return True

    async def _play(self, text: str, wav: bytes, gen: int) -> None:
        client, key = self._get_client(), self._get_key()
        if client is None or key is None:
            log.warning("device not connected, dropping: %r", text)
            return
        dur = wav_seconds(wav, self.tts.sample_rate)
        url = self.audio.add_wav(wav)
        t0 = time.monotonic()
        before = self._state.name
        bus.set_state("speaking")
        client.media_player_command(key, media_url=url, announcement=True)
        started = await self._wait_state(True, 4.0)
        t1 = time.monotonic()
        if gen != self.generation:  # stop was said while the clip was being handed over
            self._stop_playing()
            log.info("stop arrived while sending %r: cut it off", config.shown(text[:40]))
            return
        if t1 - t0 > 1.0:
            log.info("slow start (%.2fs): the media player was %s when the clip was sent", t1 - t0, before)
        if started:
            await self._wait_state(False, dur + 5.0)
        else:  # the device never reported playing: fall back to the clip length
            log.warning("no PLAYING state seen, waiting %.1fs", dur)
            await asyncio.sleep(dur)
        log.info("played %.1fs clip: start lag %.2fs, total %.2fs: %r", dur, t1 - t0, time.monotonic() - t0,
                 config.shown(text[:60]))
