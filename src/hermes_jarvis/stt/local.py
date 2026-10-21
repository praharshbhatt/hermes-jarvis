from __future__ import annotations

import asyncio
import logging

import numpy as np

from .. import config

log = logging.getLogger("hermes_jarvis.stt.local")


class LocalSTT:
    """Fully local transcription with faster-whisper (pip install 'hermes-jarvis[local-stt]'). No audio leaves the machine."""

    name = "local"

    def __init__(self) -> None:
        self._model = None

    def check(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper is not installed: pip install 'hermes-jarvis[local-stt]'"
        return True, f"faster-whisper, model {config.cfg.stt.local_model}"

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            log.info("loading Whisper model %s (first use downloads it)", config.cfg.stt.local_model)
            self._model = WhisperModel(config.cfg.stt.local_model, device="auto", compute_type="int8")
        return self._model

    def _run(self, pcm: bytes) -> str:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._load().transcribe(audio, language=config.cfg.stt.language, beam_size=1,
                                              vad_filter=False, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()

    async def transcribe_pcm(self, pcm: bytes) -> str:
        return await asyncio.to_thread(self._run, pcm)
