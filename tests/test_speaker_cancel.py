"""Saying stop clears the queue and silences the rest of the turn that was running."""
import asyncio

from hermes_jarvis.speaker import Speaker


class FakeTTS:
    sample_rate = 22050

    def synth_wav(self, text):
        return b"\0" * 44 + b"\0" * 2000


def test_cancel_drops_queue_and_the_rest_of_the_old_turn():
    async def go():
        sp = Speaker(FakeTTS(), None, lambda: None, lambda: None)  # worker not started: only the queue matters
        gen = sp.generation
        await sp.say("one", gen)
        await sp.say("two", gen)
        assert sp._q.qsize() == 2 and sp.speaking
        sp.cancel()
        assert sp._q.qsize() == 0 and not sp.speaking and sp.generation == gen + 1
        await sp.say("rest of the old turn", gen)            # same turn, after stop: dropped
        assert sp._q.qsize() == 0
        sp.canned = [("ack", b"x" * 100)]
        assert await sp.say_canned(gen) is None               # the old turn's ack: dropped
        await sp.say("a new turn", sp.generation)             # the next turn is spoken
        assert sp._q.qsize() == 1
        await sp.say("proactive", None)                       # deliveries carry no generation: spoken
        assert sp._q.qsize() == 2

    asyncio.run(go())


def test_clip_urls_are_unguessable_and_expire():
    from hermes_jarvis.audio_server import AudioServer
    srv = AudioServer(port=1)
    a, b = srv.add_wav(b"x"), srv.add_wav(b"y")
    assert a != b and a.endswith(".wav") and len(a.rsplit("/", 1)[1]) >= 16 and not a.rsplit("/", 1)[1].startswith("1.")
    for k in list(srv._clips):
        srv._clips[k] = (srv._clips[k][0], 0.0)   # pretend they are old
    srv.add_wav(b"z")
    assert len(srv._clips) == 1                    # the old ones were dropped


def test_stop_flashes_the_core_and_then_returns_to_idle():
    from hermes_jarvis.events import bus

    async def go():
        sp = Speaker(FakeTTS(), None, lambda: None, lambda: None)
        q = bus.subscribe()
        bus.set_state("speaking")
        sp.cancel()
        states = [e["state"] for e in (q.get_nowait() for _ in range(q.qsize())) if e["type"] == "state"]
        await asyncio.sleep(1.4)
        late = [e["state"] for e in (q.get_nowait() for _ in range(q.qsize())) if e["type"] == "state"]
        return states, late

    states, late = asyncio.run(go())
    assert states == ["speaking", "stopped"] and late == ["idle"]


def test_cancel_tells_the_device_to_stop_the_playing_clip():
    from aioesphomeapi import MediaPlayerCommand

    sent = []

    class Client:
        def media_player_command(self, key, **kw):
            sent.append((key, kw))

    async def go():
        sp = Speaker(FakeTTS(), None, lambda: Client(), lambda: 7)
        sp.cancel()

    asyncio.run(go())
    assert sent[0] == (7, {"command": MediaPlayerCommand.STOP, "announcement": True})


def test_a_stop_during_handover_cuts_the_clip_off():
    from aioesphomeapi import MediaPlayerCommand, MediaPlayerState

    sent = []

    class Audio:
        def add_wav(self, wav):
            return "http://x/a.wav"

    class Client:
        def media_player_command(self, key, **kw):
            sent.append(kw)

    async def go():
        sp = Speaker(FakeTTS(), Audio(), lambda: Client(), lambda: 7)
        gen = sp.generation
        task = asyncio.create_task(sp._play("hi", b"\0" * 44 + b"\0" * 2000, gen))
        await asyncio.sleep(0.05)
        sp.generation += 1                       # stop word arrives while the clip is being sent
        sp.on_media_state(MediaPlayerState.PLAYING)
        await task

    asyncio.run(go())
    assert {"command": MediaPlayerCommand.STOP, "announcement": True} in sent
