from __future__ import annotations

import aiohttp

from .. import config


class ElevenLabsSTT:
    name = "elevenlabs"
    URL = "https://api.elevenlabs.io/v1/speech-to-text"

    def __init__(self, model: str = "scribe_v2"):
        self.model = model

    def check(self) -> tuple[bool, str]:
        ok = bool(config.secret("ELEVENLABS_API_KEY"))
        return ok, "key set" if ok else "missing: set ELEVENLABS_API_KEY"

    async def transcribe_pcm(self, pcm: bytes) -> str:
        key = config.secret("ELEVENLABS_API_KEY")
        if not key:
            return ""
        form = aiohttp.FormData()
        form.add_field("model_id", self.model)
        form.add_field("language_code", config.cfg.stt.language)
        form.add_field("tag_audio_events", "false")
        form.add_field("file_format", "pcm_s16le_16")  # raw PCM is the low-latency input per the API docs
        form.add_field("file", pcm, filename="audio.pcm", content_type="application/octet-stream")
        async with aiohttp.ClientSession() as s:
            async with s.post(self.URL, headers={"xi-api-key": key}, data=form,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status >= 400:
                    raise RuntimeError(f"elevenlabs {r.status}: {(await r.text())[:200]}")
                j = await r.json()
        return (j.get("text") or "").strip()
