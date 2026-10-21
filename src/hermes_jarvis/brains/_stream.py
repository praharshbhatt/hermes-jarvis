"""Parse an OpenAI-style chat completions SSE stream into events.

Yields {"type": "text", "delta": str} for content and {"type": "tool", ...} for Hermes tool-progress events.
Comment lines (keepalives starting with ":") are skipped.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import aiohttp


async def iter_chat_stream(resp: aiohttp.ClientResponse) -> AsyncIterator[dict]:
    event = None
    async for raw in resp.content:
        line = raw.decode("utf-8", "replace").strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            j = json.loads(data)
        except ValueError:
            continue
        if event:
            if event == "hermes.tool.progress":
                yield {"type": "tool", **j}
            event = None
            continue
        choice = (j.get("choices") or [{}])[0]
        delta = (choice.get("delta") or {}).get("content")
        if delta:
            yield {"type": "text", "delta": delta}
