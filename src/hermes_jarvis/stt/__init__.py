"""Speech to text. `stt.provider` in config.yaml picks one; `stt.compare_with` runs a second in parallel for logging."""
from __future__ import annotations

import asyncio
import logging
import time

from .. import config
from .base import SttProvider

log = logging.getLogger("hermes_jarvis.stt")


def make_provider(name: str) -> SttProvider:
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsSTT
        return ElevenLabsSTT()
    if name == "deepgram":
        from .deepgram import DeepgramSTT
        return DeepgramSTT()
    if name == "openai":
        from .openai_stt import OpenAISTT
        return OpenAISTT()
    if name == "local":
        from .local import LocalSTT
        return LocalSTT()
    raise ValueError(f"unknown stt provider {name!r} (elevenlabs, deepgram, openai, local)")


class STT:
    """Runs the main provider and, optionally, a comparison provider. Only the main provider's text is used."""

    def __init__(self) -> None:
        c = config.cfg.stt
        self.main = make_provider(c.provider)
        self.other = make_provider(c.compare_with) if c.compare_with else None

    def providers(self) -> list[SttProvider]:
        return [self.main] + ([self.other] if self.other else [])

    async def transcribe(self, pcm: bytes) -> str:
        async def one(p: SttProvider):
            t0 = time.monotonic()
            try:
                text = await p.transcribe_pcm(pcm)
            except Exception as e:
                log.warning("%s failed: %s", p.name, e)
                text = ""
            return p.name, text, time.monotonic() - t0

        results = await asyncio.gather(*(one(p) for p in self.providers()))
        for name, text, dt in results:
            log.info("STT %-10s %.2fs %r", name, dt, config.shown(text))
        return results[0][1]
