"""Hermes agent brain (https://hermes-agent.nousresearch.com): its OpenAI-compatible gateway, streamed.

One call per spoken turn. A continued session sends only the new message plus the session header; Hermes keeps
the transcript. Profiles other than "default" live under /p/<name>/ and need their own key, read from
<api_key_env>_<NAME> (for example HERMES_API_KEY_WORK).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import aiohttp

from .. import config
from ..settings import settings
from ._stream import iter_chat_stream

log = logging.getLogger("hermes_jarvis.brain.hermes")


class HermesBrain:
    name = "hermes"
    supports_profiles = True
    supports_sessions = True

    def __init__(self) -> None:
        self._http: aiohttp.ClientSession | None = None

    def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            # no total timeout: jobs can run for minutes. Hermes sends a keepalive every 10 s.
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_read=90))
        return self._http

    @staticmethod
    def _base() -> str:
        return config.cfg.brain.base_url.rstrip("/")

    @staticmethod
    def key_for(profile: str) -> str:
        env = config.cfg.brain.api_key_env
        return config.secret(env if profile == "default" else f"{env}_{profile.upper()}")

    def _target(self, profile: str) -> tuple[str, str]:
        prefix = "" if profile == "default" else f"/p/{profile}"
        model = config.cfg.brain.model if profile == "default" else profile
        return f"{self._base()}{prefix}", model

    async def list_sessions(self, profile: str = "default", limit: int = 100, source: str | None = None) -> list[dict]:
        """Recent sessions of one profile, newest activity first. Filter by source on the server: an unfiltered
        list can be dominated by scheduled-job sessions and take seconds."""
        root, _ = self._target(profile)
        async with self._session().get(
                f"{root}/api/sessions", params={"limit": str(limit), **({"source": source} if source else {})},
                headers={"Authorization": f"Bearer {self.key_for(profile)}"},
                timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                raise RuntimeError(f"sessions {profile}: HTTP {r.status}")
            data = (await r.json())["data"]
        return sorted(data, key=lambda s: s.get("last_active") or s.get("started_at") or 0, reverse=True)

    async def turn(self, text: str, session_id: str | None = None, profile: str = "default") -> AsyncIterator[dict]:
        root, model = self._target(profile)
        headers = {"Authorization": f"Bearer {self.key_for(profile)}"}
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id
        body = {"model": model, "stream": True,
                "messages": [{"role": "system", "content": settings.get("voice_prompt")},
                             {"role": "user", "content": text}]}
        try:
            async with self._session().post(f"{root}/v1/chat/completions", json=body, headers=headers) as r:
                if r.status != 200:
                    detail = (await r.text())[:200]
                    log.warning("hermes HTTP %s: %s", r.status, detail)
                    yield {"type": "error", "status": r.status, "detail": detail}
                    return
                yield {"type": "session", "id": r.headers.get("X-Hermes-Session-Id", session_id)}
                async for ev in iter_chat_stream(r):
                    yield ev
        except (aiohttp.ClientError, TimeoutError) as e:
            log.warning("hermes connection problem: %s", e)
            yield {"type": "error", "status": 0, "detail": str(e)}
            return
        yield {"type": "done"}

    async def check(self) -> list[tuple[str, bool, str]]:
        out: list[tuple[str, bool, str]] = []
        base = self._base()
        s = self._session()
        try:
            async with s.get(f"{base}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                out.append(("Hermes gateway reachable", r.status == 200, f"{base}/health -> HTTP {r.status}"))
        except Exception as e:
            return [("Hermes gateway reachable", False, f"{base}: {type(e).__name__}: {e}")]
        for p in [p for p in settings.get("profiles") if p["enabled"]]:
            root, _ = self._target(p["name"])
            key = self.key_for(p["name"])
            label = f"Hermes profile '{p['name']}' key"
            if not key:
                env = config.cfg.brain.api_key_env
                var = env if p["name"] == "default" else env + "_" + p["name"].upper()
                out.append((label, False, f"missing: set {var}"))
                continue
            try:
                async with s.get(f"{root}/v1/models", headers={"Authorization": f"Bearer {key}"},
                                 timeout=aiohttp.ClientTimeout(total=8)) as r:
                    out.append((label, r.status == 200, "accepted" if r.status == 200 else f"HTTP {r.status} (wrong key?)"))
            except Exception as e:
                out.append((label, False, f"{type(e).__name__}: {e}"))
        return out

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()
