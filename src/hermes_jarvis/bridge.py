"""The voice bridge: talks to the ESPHome voice device as an API client (the role Home Assistant normally plays),
runs the wake -> end-of-speech -> speech-to-text -> brain -> text-to-speech pipeline, and plays the answer back.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from datetime import datetime

import numpy as np
from aioesphomeapi import (
    APIClient,
    APIConnectionError,
    Event,
    EventInfo,
    InvalidEncryptionKeyAPIError,
    MediaPlayerEntityState,
    MediaPlayerInfo,
    RequiresEncryptionAPIError,
)
from aioesphomeapi import VoiceAssistantEventType as Ev

from . import config, discovery
from .admin import AdminServer
from .audio_server import AudioServer
from .brains import make_brain
from .conversation import Conversation
from .errors import UserError
from .events import bus
from .router import Router
from .settings import settings
from .speaker import Speaker
from .stt import STT
from .tts import PiperTTS
from .vad import Endpointer

log = logging.getLogger("hermes_jarvis.bridge")


def _rms(pcm: bytes) -> float:
    """Loudness of a chunk of 16-bit audio as 0 to 1 (only this number is shared with the UI, never the audio)."""
    x = np.frombuffer(pcm, dtype=np.int16)
    if not x.size:
        return 0.0
    return min(1.0, float(np.sqrt(np.mean(np.square(x.astype(np.float32)))) / 6000.0))


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class VoiceBridge:
    def __init__(self) -> None:
        self.client: APIClient | None = None
        self.media_key: int | None = None
        self.entities: list = []        # the device's entities and their latest states, for the admin UI
        self.states: dict = {}
        try:
            self.tts = PiperTTS()
        except OSError as e:  # includes a missing voice file and a failed download
            raise UserError(
                f"could not load the speech voice {config.cfg.tts.voice!r}: {e}. Download it with "
                f"`hermes-jarvis voices download {config.cfg.tts.voice}` or set tts.voice to a local .onnx file.") from e
        self.stt = STT()
        self.audio = AudioServer()
        self.ep = Endpointer()
        self.brain = make_brain()
        self.speaker = Speaker(self.tts, self.audio, lambda: self.client, lambda: self.media_key)
        self.router = Router(self.brain)
        self.conv = Conversation(self.brain, self.speaker, self.router)
        self.admin = AdminServer(self)
        self.device_name = ""
        self._retry_now = asyncio.Event()  # set to cut a reconnect back-off short (after adopting a device)
        self.active = False            # a voice session is capturing audio right now
        self._pcm = bytearray()
        self._t: dict[str, float] = {}
        self._reply_task: asyncio.Task | None = None
        self._followup_next = False    # the next session was started by us after a question, not by a wake word

    # ----- connection -----
    def nudge_reconnect(self) -> None:
        """Try the device again now instead of waiting out the back-off."""
        self._retry_now.set()

    async def apply_voice(self) -> None:
        """The voice setting changed: load it in a thread, then re-render the acknowledgements in it."""
        name = settings.get("tts_voice")
        if name == self.tts.name:
            return
        try:
            await asyncio.to_thread(self.tts.set_voice, name)
        except Exception:
            log.exception("could not switch to voice %s; keeping %s", name, self.tts.name)
            return
        await self.speaker.prerender(settings.acks())
        log.info("speech voice is now %s", name)

    def _send(self, event, data: dict) -> None:
        """Tell the device what the pipeline is doing. A no-op if the device just disconnected."""
        if self.client is not None:
            self.client.send_voice_assistant_event(event, data)

    async def run(self) -> None:
        try:
            await self.audio.start()
        except OSError as e:
            raise UserError(f"cannot listen on port {config.cfg.audio.port} for speech clips: {e} "
                            "(is hermes-jarvis already running? change audio.port)") from e
        log.info("speech clips are served at %s", self.audio.base)
        await self.speaker.prerender(settings.acks())
        self.speaker.start()
        try:
            await self.admin.start()
        except OSError as e:
            raise UserError(f"cannot start the admin UI on {config.cfg.admin.host}:{config.cfg.admin.port}: {e} "
                            "(change admin.port, or leave ADMIN_PASSWORD unset to turn it off)") from e
        self._clean_recordings()
        backoff = 2.0
        warned = False
        while True:
            try:
                host, name = await discovery.resolve_host()
                if not host:
                    if not warned:
                        log.warning("no voice device found. Plug it in and power it on, then run `hermes-jarvis adopt`, "
                                    "or set device.host in config.yaml. Retrying every %.0f s.", backoff)
                        warned = True
                else:
                    warned = False
                    await self._connect_and_serve(host)
                    backoff = 2.0
            except RequiresEncryptionAPIError:
                log.error("the device needs an encryption key. Run `hermes-jarvis adopt`, or set ESPHOME_API_KEY.")
            except InvalidEncryptionKeyAPIError:
                log.error("the saved encryption key does not match the device (re-flashed or factory reset?). "
                          "Run `hermes-jarvis adopt` again.")
            except (APIConnectionError, OSError, TimeoutError) as e:
                log.warning("device connection problem: %s (retry in %.0fs)", e, backoff)
            except asyncio.CancelledError:
                raise
            except Exception:  # never let one bad connection attempt end the service
                log.exception("unexpected error talking to the device (retry in %.0fs)", backoff)
            try:
                await asyncio.wait_for(self._retry_now.wait(), backoff)
            except TimeoutError:
                pass
            self._retry_now.clear()
            backoff = min(backoff * 2, 30.0)

    async def _connect_and_serve(self, host: str) -> None:
        lost = asyncio.Event()

        async def on_stop(_expected):
            lost.set()

        c = APIClient(host, int(config.cfg.device.port), None, noise_psk=config.device_key(),
                      keepalive=5.0)  # notice a rebooted or vanished device within seconds and re-subscribe
        await c.connect(on_stop=on_stop, login=True)
        self.client = c
        info = await c.device_info()
        ents, _ = await c.list_entities_services()
        media = next((e for e in ents if isinstance(e, MediaPlayerInfo)), None)
        if media is None:
            await c.disconnect()
            raise APIConnectionError(f"{info.name} has no media player: not a voice device?")
        self.media_key = media.key
        self.entities, self.states = ents, {}
        self.device_name = info.name
        bus.set_device(True, info.name)
        log.info("connected to %s at %s (esphome %s)", info.name, host, info.esphome_version)

        stop_key = next((e.key for e in ents if isinstance(e, EventInfo) and e.object_id == "stop_word"), None)
        if stop_key is None:
            log.warning("the device has no 'Stop word' event (firmware without the hermes-jarvis changes): "
                        "saying stop will not clear the queued speech")

        def on_state(st) -> None:
            self.states[st.key] = st
            if isinstance(st, MediaPlayerEntityState) and st.key == self.media_key:
                self.speaker.on_media_state(st.state)
            elif isinstance(st, Event) and st.key == stop_key and st.event_type == "stop":
                log.info("stop word heard")
                self.speaker.cancel()

        c.subscribe_states(on_state)
        c.subscribe_voice_assistant(handle_start=self.on_start, handle_stop=self.on_stop, handle_audio=self.on_audio)
        await self._ensure_wake_word(c)
        await lost.wait()
        log.warning("device disconnected")
        self.client = None
        bus.set_device(False)
        bus.set_state("idle")
        self.entities, self.states = [], {}

    async def _ensure_wake_word(self, c: APIClient) -> None:
        """A freshly flashed device has no active wake word (Home Assistant used to pick one), so it would never wake.
        Only the connection that subscribed to voice can see or change this."""
        want = config.cfg.device.wake_word
        if not want:
            return
        try:
            vc = await c.get_voice_assistant_configuration(timeout=5.0)
            if vc.active_wake_words or not vc.max_active_wake_words:
                return
            ids = [w.id for w in vc.available_wake_words]
            if want not in ids:
                log.warning("wake word %r is not on the device (it has: %s)", want, ", ".join(ids) or "none")
                return
            await c.set_voice_assistant_configuration([want])
            log.info("no wake word was active: switched on %r", want)
        except (TimeoutError, APIConnectionError) as e:
            log.warning("could not check the wake word: %s", e)

    # ----- voice assistant callbacks -----
    async def on_start(self, conversation_id: str, flags: int, audio_settings, wake_word: str | None) -> int | None:
        followup, self._followup_next = self._followup_next, False
        log.info("%s", "listening for the answer" if followup else f"wake: {wake_word!r}")
        self._t = {"wake": time.monotonic()}
        self._pcm = bytearray()
        self.ep.reset(silence_s=float(settings.get("vad_silence_s")),
                      no_speech_s=float(settings.get("followup_no_speech_s" if followup else "no_speech_s")))
        self.active = True
        bus.set_state("followup" if followup else "wake")
        self._send(Ev.VOICE_ASSISTANT_RUN_START, {})
        self._send(Ev.VOICE_ASSISTANT_STT_START, {})
        return 0  # 0 = audio comes over the API connection

    async def on_audio(self, data: bytes, data2: bytes | None = None) -> None:
        # data2 is an optional second channel from newer firmware; the first channel is what we use
        if not self.active:
            return
        self._pcm += data
        bus.level(_rms(data))
        for ev in self.ep.feed(data):
            now = time.monotonic()
            if ev == "speech_start":
                bus.set_state("speech")
                self._t["speech_start"] = now
                self._send(Ev.VOICE_ASSISTANT_STT_VAD_START, {})
            elif ev in ("speech_end", "no_speech"):
                self._t["speech_end"] = now
                self.active = False
                if ev == "no_speech":
                    bus.set_state("idle")
                    log.info("no speech detected")
                    self._send(
                        Ev.VOICE_ASSISTANT_ERROR, {"code": "stt-no-text-recognized", "message": "no speech"})
                    self._send(Ev.VOICE_ASSISTANT_RUN_END, {})
                else:
                    bus.set_state("thinking")
                    self._send(Ev.VOICE_ASSISTANT_STT_VAD_END, {})
                    self._reply_task = asyncio.create_task(self._reply(bytes(self._pcm)))

    async def on_stop(self, abort: bool) -> None:
        log.info("device stop (abort=%s)", abort)
        self.active = False

    # ----- reply: the brain answers, sentences are spoken as they arrive -----
    async def _reply(self, pcm: bytes) -> None:
        t = self._t
        run_ended = False
        listen_gen: int | None = None

        async def end_run() -> None:
            nonlocal run_ended
            if not run_ended:
                run_ended = True
                self._send(Ev.VOICE_ASSISTANT_RUN_END, {})

        try:
            self._save_recording(pcm)
            t0 = time.monotonic()
            try:
                text = await self.stt.transcribe(bytes(pcm))
            except Exception as e:  # keep the loop alive if STT fails
                log.warning("STT failed: %s", e)
                text = ""
            t["stt_done"] = time.monotonic()
            log.info("heard=%r | speech %.1fs | stt %.2fs | end-of-speech -> transcript %.2fs", config.shown(text),
                     t["speech_end"] - t.get("speech_start", t["speech_end"]), t["stt_done"] - t0,
                     t["stt_done"] - t["speech_end"])
            if not text:
                bus.set_state("idle")
                self._send(
                    Ev.VOICE_ASSISTANT_ERROR, {"code": "stt-no-text-recognized", "message": "no text"})
                return
            bus.transcript("user", text)
            self._send(Ev.VOICE_ASSISTANT_STT_END, {"text": text})
            # the pipeline run ends when speech starts, so the device is free for the wake word during long jobs
            listen_gen = await self.conv.handle(text, on_speaking=end_run)
        except Exception:
            log.exception("reply failed")
            self._send(
                Ev.VOICE_ASSISTANT_ERROR, {"code": "bridge-error", "message": "reply failed"})
        finally:
            await end_run()
        if listen_gen is not None:
            await self._listen_again(listen_gen)

    async def _listen_again(self, gen: int) -> None:
        """The last thing said was a question: once the reply has finished playing, listen for the answer."""
        await self.speaker.drain()
        if self.speaker.generation != gen or self.active or self.client is None:
            return  # stop was said, the user already started talking, or the device is gone
        self._followup_next = True
        if not await self.speaker.start_listening():
            self._followup_next = False

    async def close(self) -> None:
        """Stop everything cleanly (called on SIGTERM and Ctrl-C)."""
        if self._reply_task:
            self._reply_task.cancel()
        await self.speaker.stop()
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:  # noqa: S110 (already shutting down)
                pass
        await self.admin.stop()
        await self.audio.stop()
        await self.brain.close()
        await self.router.close()

    # ----- recordings (off unless privacy.save_recordings is set) -----
    def _save_recording(self, pcm: bytes) -> None:
        if not config.cfg.privacy.save_recordings:
            return
        d = config.cfg.data_path("recordings")
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{datetime.now():%Y%m%d-%H%M%S}.wav").write_bytes(pcm_to_wav(pcm))

    def _clean_recordings(self) -> None:
        d = config.cfg.data_path("recordings")
        if not d.exists():
            return
        cutoff = time.time() - float(config.cfg.privacy.recordings_keep_days) * 86400
        gone = 0
        for f in d.glob("*.wav"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                gone += 1
        if gone:
            log.info("removed %d recording(s) older than %s days", gone, config.cfg.privacy.recordings_keep_days)
