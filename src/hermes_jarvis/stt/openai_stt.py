from __future__ import annotations

import aiohttp

from .. import config
from .base import pcm_to_wav


class OpenAISTT:
    """OpenAI's /audio/transcriptions, or any server that implements it (self-hosted Whisper servers do)."""

    name = "openai"

    def check(self) -> tuple[bool, str]:
        local = not config.cfg.stt.openai_base_url.startswith("https://api.openai.com")
        ok = local or bool(config.secret("OPENAI_API_KEY"))
        return ok, "ready" if ok else "missing: set OPENAI_API_KEY"

    async def transcribe_pcm(self, pcm: bytes) -> str:
        c = config.cfg.stt
        key = config.secret("OPENAI_API_KEY")
        form = aiohttp.FormData()
        form.add_field("model", c.openai_model)
        form.add_field("language", c.language)
        form.add_field("file", pcm_to_wav(pcm), filename="audio.wav", content_type="audio/wav")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{c.openai_base_url.rstrip('/')}/audio/transcriptions", headers=headers, data=form,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status >= 400:
                    raise RuntimeError(f"openai stt {r.status}: {(await r.text())[:200]}")
                j = await r.json()
        return (j.get("text") or "").strip()
