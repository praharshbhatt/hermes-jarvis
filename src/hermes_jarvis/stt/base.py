"""Shared pieces for speech-to-text providers. Every provider takes raw 16 kHz 16-bit mono PCM and returns text."""
from __future__ import annotations

import io
import wave
from typing import Protocol


class SttProvider(Protocol):
    name: str

    async def transcribe_pcm(self, pcm: bytes) -> str: ...

    def check(self) -> tuple[bool, str]:
        """(ok, detail) for `hermes-jarvis doctor`: is the provider usable (key present, package installed)?"""
        ...


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()
