"""Piper text to speech (CPU). Returns WAV bytes, one sentence at a time so playback can start early."""
from __future__ import annotations

import io
import wave
from collections.abc import Iterator

from piper import PiperVoice, SynthesisConfig

from ..settings import settings
from . import voices


class PiperTTS:
    def __init__(self, voice: str | None = None):
        self.name = ""
        self.set_voice(voice or settings.get("tts_voice"))

    def set_voice(self, voice: str) -> None:
        """Load a voice (downloading it first if it is a catalog name). Blocking: call it from a thread at runtime.
        The previous voice stays in use until the new one has loaded, so a failure changes nothing."""
        path = voices.ensure(voice)
        loaded = PiperVoice.load(str(path), config_path=f"{path}.json")
        self.voice, self.sample_rate, self.name = loaded, loaded.config.sample_rate, voice

    @staticmethod
    def _cfg() -> SynthesisConfig:
        # Read per call so the admin UI applies at once. length_scale > 1 is slower.
        return SynthesisConfig(length_scale=float(settings.get("piper_length_scale")),
                               noise_scale=float(settings.get("piper_noise_scale")),
                               noise_w_scale=float(settings.get("piper_noise_w_scale")))

    def synth_pcm(self, text: str) -> Iterator[bytes]:
        """Yield int16 PCM byte chunks, one per sentence."""
        for chunk in self.voice.synthesize(text, syn_config=self._cfg()):
            yield chunk.audio_int16_bytes

    def synth_wav(self, text: str) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            for pcm in self.synth_pcm(text):
                w.writeframes(pcm)
        return buf.getvalue()
