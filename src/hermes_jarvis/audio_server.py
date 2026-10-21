"""Tiny HTTP server the device's media player pulls TTS audio from."""
import secrets
import time

from aiohttp import web

from . import config

MAX_CLIPS = 200


class AudioServer:
    def __init__(self, port: int | None = None):
        self.port = port or config.cfg.audio.port
        self.base = f"http://{config.lan_ip()}:{self.port}"
        self._clips: dict[str, tuple[bytes, float]] = {}
        self._runner: web.AppRunner | None = None

    def add_wav(self, wav: bytes) -> str:
        """Store a clip and return the URL the device should fetch."""
        self._expire()
        while len(self._clips) >= MAX_CLIPS:  # a hard cap, on top of the time limit
            self._clips.pop(next(iter(self._clips)))
        cid = f"{secrets.token_urlsafe(12)}.wav"  # unguessable: clips hold what the assistant said
        self._clips[cid] = (wav, time.time())
        return f"{self.base}/audio/{cid}"

    def _expire(self, ttl: float = 600.0) -> None:
        now = time.time()
        for k in [k for k, (_, t) in self._clips.items() if now - t > ttl]:
            del self._clips[k]

    async def _get(self, request: web.Request) -> web.Response:
        item = self._clips.get(request.match_info["cid"])
        if item is None:
            raise web.HTTPNotFound()
        return web.Response(body=item[0], content_type="audio/wav")

    async def _health(self, _request: web.Request) -> web.Response:
        return web.json_response({"ok": True})  # for container health checks

    async def start(self) -> None:
        app = web.Application()
        app.add_routes([web.get("/audio/{cid}", self._get), web.get("/healthz", self._health)])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "0.0.0.0", self.port).start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
