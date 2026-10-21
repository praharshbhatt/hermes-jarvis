"""A small in-process event bus: the pipeline publishes what is happening, the admin UI's live view subscribes.

Events carry states, short text and routing decisions, never audio and never secrets. Text respects
`privacy.save_transcripts`: when it is off, transcript text is replaced by an empty string and `hidden` is set.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque

from . import config

# Pipeline states, in the order a normal turn passes through them.
STATES = ("idle", "wake", "listening", "speech", "thinking", "speaking", "stopped", "followup")
SUBSCRIBER_QUEUE = 200


class EventBus:
    def __init__(self) -> None:
        self.state = "idle"
        self.device_connected = False
        self.device_name = ""
        self._subs: set[asyncio.Queue] = set()
        self._recent: deque = deque(maxlen=60)
        self._seq = 0
        self._last_level = 0.0

    # ----- publishing -----
    def publish(self, type_: str, **data) -> dict:
        self._seq += 1
        event = {"id": self._seq, "ts": round(time.time(), 3), "type": type_, **data}
        if type_ != "level":  # levels are frequent and only matter live
            self._recent.append(event)
        for q in list(self._subs):
            if q.full():
                try:
                    q.get_nowait()  # a slow viewer loses its oldest event, never blocks the pipeline
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)
        return event

    def set_state(self, state: str, **data) -> None:
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        self.state = state
        self.publish("state", state=state, **data)

    def transcript(self, role: str, text: str) -> None:
        shown = config.cfg.privacy.save_transcripts
        self.publish("transcript", role=role, text=text if shown else "", hidden=not shown)

    def tool(self, tool: str, label: str, status: str) -> None:
        shown = config.cfg.privacy.save_transcripts  # tool labels can contain what you asked about
        self.publish("tool", tool=str(tool)[:60], label=(str(label)[:120] if shown else ""), status=str(status)[:20])

    def route(self, profile: str, reason: str, router_ms: int, resumed: bool) -> None:
        self.publish("route", profile=profile, reason=reason, router_ms=int(router_ms), resumed=resumed)

    def level(self, value: float) -> None:
        """Microphone loudness (0 to 1), at most ten times a second. A number only: no audio leaves the bridge."""
        now = time.monotonic()
        if now - self._last_level >= 0.1:
            self._last_level = now
            self.publish("level", value=round(max(0.0, min(1.0, value)), 3))

    def set_device(self, connected: bool, name: str = "") -> None:
        self.device_connected, self.device_name = connected, name if connected else self.device_name
        self.publish("device", connected=connected, name=self.device_name)

    # ----- subscribing -----
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def snapshot(self) -> dict:
        return {"state": self.state, "device": {"connected": self.device_connected, "name": self.device_name},
                "recent": list(self._recent)[-25:]}


bus = EventBus()
