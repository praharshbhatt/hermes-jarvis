"""The event bus the live view subscribes to."""
import asyncio

import pytest

from hermes_jarvis import config
from hermes_jarvis.events import SUBSCRIBER_QUEUE, EventBus


def test_subscribers_receive_events_in_order_with_ids():
    async def go():
        bus = EventBus()
        q = bus.subscribe()
        bus.set_state("wake")
        bus.set_state("speech")
        bus.route("work", "jev-resume", 250, True)
        got = [q.get_nowait() for _ in range(3)]
        return bus, got

    bus, got = asyncio.run(go())
    assert [e["type"] for e in got] == ["state", "state", "route"]
    assert [e["state"] for e in got[:2]] == ["wake", "speech"] and got[2]["router_ms"] == 250
    assert got[0]["id"] < got[1]["id"] < got[2]["id"] and bus.state == "speech"


def test_unknown_states_are_rejected():
    with pytest.raises(ValueError):
        EventBus().set_state("exploding")


def test_unsubscribed_queues_get_nothing_and_a_slow_viewer_never_blocks():
    async def go():
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.set_state("wake")
        assert q.empty()
        slow = bus.subscribe()
        for i in range(SUBSCRIBER_QUEUE + 50):    # a viewer that never reads
            bus.publish("tool", tool="t", label=str(i), status="running")
        return slow.qsize(), slow.get_nowait()["id"]

    size, oldest = asyncio.run(go())
    assert size == SUBSCRIBER_QUEUE and oldest > 1      # the oldest events were dropped, nothing raised


def test_transcript_text_respects_the_privacy_setting():
    async def go():
        bus = EventBus()
        q = bus.subscribe()
        bus.transcript("user", "what is my balance")
        shown = q.get_nowait()
        config.use({"privacy": {"save_transcripts": False}}, base_dir=config.cfg.base_dir)
        bus.transcript("user", "what is my balance")
        bus.tool("terminal", "cat finance.csv", "running")
        return shown, q.get_nowait(), q.get_nowait()

    shown, hidden, tool = asyncio.run(go())
    assert shown["text"] == "what is my balance" and not shown["hidden"]
    assert hidden["text"] == "" and hidden["hidden"] is True
    assert tool["label"] == "" and tool["tool"] == "terminal"           # what the tool touched is hidden too


def test_levels_are_throttled_clamped_and_not_replayed(monkeypatch):
    async def go():
        bus = EventBus()
        q = bus.subscribe()
        for v in (0.1, 0.2, 5.0, -3.0):
            bus.level(v)                       # all within 100 ms: only the first passes
        assert q.qsize() == 1 and q.get_nowait()["value"] == 0.1
        bus._last_level = 0
        bus.level(5.0)
        assert q.get_nowait()["value"] == 1.0
        bus._last_level = 0
        bus.level(-1)
        assert q.get_nowait()["value"] == 0.0
        return bus.snapshot()

    snap = asyncio.run(go())
    assert all(e["type"] != "level" for e in snap["recent"])


def test_snapshot_has_state_device_and_recent_events():
    async def go():
        bus = EventBus()
        bus.set_device(True, "voice-1")
        bus.set_state("thinking")
        bus.transcript("user", "hello")
        return bus.snapshot()

    snap = asyncio.run(go())
    assert snap["state"] == "thinking" and snap["device"] == {"connected": True, "name": "voice-1"}
    assert [e["type"] for e in snap["recent"]] == ["device", "state", "transcript"]


def test_the_device_name_survives_a_disconnect():
    async def go():
        bus = EventBus()
        bus.set_device(True, "voice-1")
        bus.set_device(False)
        return bus.snapshot()["device"]

    assert asyncio.run(go()) == {"connected": False, "name": "voice-1"}
