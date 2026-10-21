"""Any OpenAI-compatible chat completions endpoint: OpenAI, Ollama, LM Studio, vLLM, OpenRouter, and so on.

The endpoint is stateless, so the conversation history is kept here (in memory, saved to the data directory so a
restart does not forget a conversation in progress). Sessions cannot be listed or resumed by title, so the router
is not used with this brain: a conversation continues within the session window, and a new one starts after it.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

import aiohttp

from .. import config, personas
from ..settings import settings
from ._stream import iter_chat_stream

log = logging.getLogger("hermes_jarvis.brain.openai")
MAX_SESSIONS = 20


class OpenAIBrain:
    name = "openai"
    supports_profiles = False
    supports_sessions = False

    def __init__(self) -> None:
        self._http: aiohttp.ClientSession | None = None
        self._sessions: dict[str, list[dict]] = {}
        try:
            self._sessions = json.loads(self._file().read_text())
        except (OSError, ValueError):
            pass

    @staticmethod
    def _file():
        return config.cfg.data_path("brain-sessions.json")

    def _save(self) -> None:
        while len(self._sessions) > MAX_SESSIONS:
            self._sessions.pop(next(iter(self._sessions)))
        f = self._file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(self._sessions))

    def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_read=90))
        return self._http

    @staticmethod
    def _root() -> str:
        base = config.cfg.brain.base_url.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    @staticmethod
    def _headers() -> dict:
        env = config.cfg.brain.api_key_env
        key = config.secret(env) if env else ""
        return {"Authorization": f"Bearer {key}"} if key else {}

    @staticmethod
    def _system_prompt() -> str:
        c = config.cfg
        persona = c.brain.system_prompt or personas.get(c.persona)["system_prompt"]
        persona = personas.render(persona, settings.get("address_as"))
        who = f" The user's name is {c.user.name}." if c.user.name else ""
        return f"{persona}{who}\n\n{settings.get('voice_prompt')}"

    async def list_sessions(self, profile: str = "default", limit: int = 100, source: str | None = None) -> list[dict]:
        return []

    async def turn(self, text: str, session_id: str | None = None, profile: str = "default") -> AsyncIterator[dict]:
        sid = session_id if session_id in self._sessions else f"oc-{uuid.uuid4().hex[:12]}"
        hist = self._sessions.setdefault(sid, [])
        keep = int(config.cfg.brain.history_messages)
        messages = ([{"role": "system", "content": self._system_prompt()}] + hist[-keep:]
                    + [{"role": "user", "content": text}])
        yield {"type": "session", "id": sid}
        reply = ""
        try:
            async with self._session().post(f"{self._root()}/chat/completions", headers=self._headers(),
                                            json={"model": config.cfg.brain.model, "stream": True,
                                                  "messages": messages}) as r:
                if r.status != 200:
                    detail = (await r.text())[:200]
                    log.warning("openai-compatible HTTP %s: %s", r.status, detail)
                    yield {"type": "error", "status": r.status, "detail": detail}
                    return
                async for ev in iter_chat_stream(r):
                    if ev["type"] == "text":
                        reply += ev["delta"]
                    yield ev
        except (aiohttp.ClientError, TimeoutError) as e:
            log.warning("connection problem: %s", e)
            yield {"type": "error", "status": 0, "detail": str(e)}
            return
        hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        del hist[:-keep]
        self._save()
        yield {"type": "done"}

    async def check(self) -> list[tuple[str, bool, str]]:
        url = f"{self._root()}/models"
        try:
            async with self._session().get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=8)) as r:
                ok = r.status == 200
                return [("Model endpoint reachable", ok, f"{url} -> HTTP {r.status}" + ("" if ok else " (key or URL wrong?)"))]
        except Exception as e:
            return [("Model endpoint reachable", False, f"{url}: {type(e).__name__}: {e}")]

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()
