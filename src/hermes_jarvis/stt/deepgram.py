from __future__ import annotations

import aiohttp

from .. import config
from .base import pcm_to_wav


class DeepgramSTT:
    name = "deepgram"
    URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, model: str = "nova-3"):
        self.model = model

    def check(self) -> tuple[bool, str]:
        ok = bool(config.secret("DEEPGRAM_API_KEY"))
        return ok, "key set" if ok else "missing: set DEEPGRAM_API_KEY"

    async def transcribe_pcm(self, pcm: bytes) -> str:
        key = config.secret("DEEPGRAM_API_KEY")
        if not key:
            return ""
        params = {"model": self.model, "smart_format": "true", "language": config.cfg.stt.language}
        headers = {"Authorization": f"Token {key}", "Content-Type": "audio/wav"}
        async with aiohttp.ClientSession() as s:
            async with s.post(self.URL, params=params, headers=headers, data=pcm_to_wav(pcm),
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                r.raise_for_status()
                j = await r.json()
        try:
            return j["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        except (KeyError, IndexError):
            return ""
