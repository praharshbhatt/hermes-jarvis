"""One spoken turn, with a fake brain, speaker and router: no device, no network."""
import asyncio

from hermes_jarvis import conversation, turnlog
from hermes_jarvis.conversation import is_question
from hermes_jarvis.router import Route
from hermes_jarvis.settings import settings


class FakeSpeaker:
    def __init__(self):
        self.generation, self.said = 0, []

    async def say(self, text, gen=None):
        if gen is None or gen == self.generation:
            self.said.append(text)

    async def say_canned(self, gen=None):
        if gen is not None and gen != self.generation:
            return None
        self.said.append("<ack>")
        return "<ack>"


class FakeRouter:
    def __init__(self, route):
        self.route_ = route

    async def route(self, text, sid, prof, last, ignore_window=False):
        return self.route_


class FakeBrain:
    name = "fake"
    supports_profiles = supports_sessions = True

    def __init__(self, events, delay=0.0):
        self.events, self.delay, self.args = events, delay, None

    async def turn(self, text, session_id=None, profile="default"):
        self.args = (text, session_id, profile)
        await asyncio.sleep(self.delay)
        for e in self.events:
            yield e
            await asyncio.sleep(0)


def ev(*parts):
    return [{"type": "session", "id": "api-new"}] + [{"type": "text", "delta": p} for p in parts] + [{"type": "done"}]


def new_route():
    return FakeRouter(Route("default", None, "jev-new"))


def turn(brain, speaker, router, text="hello"):
    return asyncio.run(conversation.Conversation(brain, speaker, router).handle(text))


def test_routed_turn_speaks_in_order_and_is_logged():
    sp = FakeSpeaker()
    brain = FakeBrain(ev("<speak>The invoice is paid. ", "It cleared on Monday.</speak>\n\nDetails: ..."))
    conv = conversation.Conversation(brain, sp, FakeRouter(Route("work", "api-old", "jev-resume", router_ms=250)))
    asyncio.run(conv.handle("status of the invoice"))
    assert brain.args == ("status of the invoice", "api-old", "work")
    assert " ".join(sp.said) == "The invoice is paid. It cleared on Monday."
    last = turnlog.recent(1)[0]
    assert last["route"]["reason"] == "jev-resume" and last["spoken_chars"] > 10 and last["first_speech_s"] is not None


def test_slow_brain_gets_a_canned_ack_first():
    settings.update({"ack_after_s": 0.1})
    sp = FakeSpeaker()
    turn(FakeBrain(ev("<speak>Done.</speak>"), delay=0.4), sp, new_route())
    assert sp.said == ["<ack>", "Done."]
    assert 0.05 < turnlog.recent(1)[0]["first_speech_s"] < 0.4   # measured to the ack, the first thing heard


def test_stop_mid_turn_silences_the_rest():
    sp = FakeSpeaker()

    class StopBrain(FakeBrain):
        async def turn(self, *a, **k):
            yield {"type": "session", "id": "s"}
            yield {"type": "text", "delta": "<speak>First sentence is spoken here. "}
            await asyncio.sleep(0)
            sp.generation += 1  # the user says stop
            yield {"type": "text", "delta": "Second sentence must stay silent.</speak>"}
            yield {"type": "done"}

    turn(StopBrain([]), sp, new_route())
    assert "Second sentence must stay silent." not in sp.said


def test_brain_error_gives_a_short_apology():
    sp = FakeSpeaker()

    class ErrBrain(FakeBrain):
        async def turn(self, *a, **k):
            yield {"type": "error", "status": 500, "detail": "x"}

    turn(ErrBrain([]), sp, new_route())
    assert sp.said and "couldn't reach" in sp.said[0]


def test_question_detection():
    assert is_question("Which one do you want, the red or the blue?")
    assert is_question('Shall I book it?"')
    assert not is_question("The invoice is paid.")
    assert not is_question("Is there anything else I can do?", ["anything else"])
    assert is_question("Is there anything else I can do?", [])


def test_listening_after_a_question_only_when_it_should():
    sp = FakeSpeaker()
    assert turn(FakeBrain(ev("<speak>Two flights found. Which one do you want?</speak>")), sp, new_route()) == 0
    assert turnlog.recent(1)[0]["listen_after"] is True
    assert turn(FakeBrain(ev("<speak>It is booked.</speak>")), FakeSpeaker(), new_route()) is None

    settings.update({"followup_enabled": False})
    assert turn(FakeBrain(ev("<speak>Which one?</speak>")), FakeSpeaker(), new_route()) is None
    settings.update({"followup_enabled": True})

    class Slow(FakeBrain):  # a request older than the window (a long job) does not open the microphone
        async def turn(self, *a, **k):
            yield {"type": "session", "id": "s"}
            await asyncio.sleep(0.15)
            yield {"type": "text", "delta": "<speak>Which one?</speak>"}
            yield {"type": "done"}

    settings.update({"followup_window_minutes": 0.001})
    assert turn(Slow([]), FakeSpeaker(), new_route()) is None
    settings.update({"followup_window_minutes": 5.0})

    sp = FakeSpeaker()

    class StopAtEnd(FakeBrain):
        async def turn(self, *a, **k):
            yield {"type": "session", "id": "s"}
            yield {"type": "text", "delta": "<speak>Which one?</speak>"}
            sp.generation += 1
            yield {"type": "done"}

    assert turn(StopAtEnd([]), sp, new_route()) is None  # stop said during the question


def test_log_text_is_hidden_when_transcripts_are_not_kept():
    from hermes_jarvis import config
    assert config.shown("what I said") == "what I said"
    config.use({"privacy": {"save_transcripts": False}}, base_dir=config.cfg.base_dir)
    assert config.shown("what I said") == "<hidden>"


def test_fixed_lines_follow_the_persona_and_how_to_address_you():
    from hermes_jarvis import config

    class Silent(FakeBrain):
        async def turn(self, *a, **k):
            yield {"type": "session", "id": "s"}
            yield {"type": "done"}

    config.use({"persona": "jarvis", "data_dir": str(config.cfg.data_path())}, base_dir=config.cfg.base_dir)
    settings.update({"address_as": "ma'am"})
    sp = FakeSpeaker()
    turn(Silent([]), sp, new_route())
    assert sp.said == ["Done, ma'am."]

    config.use({"persona": "neutral", "data_dir": str(config.cfg.data_path())}, base_dir=config.cfg.base_dir)
    sp = FakeSpeaker()

    class Broken(FakeBrain):
        async def turn(self, *a, **k):
            yield {"type": "error", "status": 500, "detail": "x"}

    turn(Broken([]), sp, new_route())
    assert sp.said == ["Sorry, I couldn't reach my systems just now."]  # no "sir" for the neutral persona


def test_the_ack_and_the_first_real_sentence_never_swap_places():
    """Whichever gets there first is spoken first; the ack is dropped if real speech already started."""
    settings.update({"ack_after_s": 0.05})
    for delay in (0.0, 0.05, 0.2):
        sp = FakeSpeaker()
        turn(FakeBrain(ev("<speak>The answer.</speak>"), delay=delay), sp, new_route())
        assert sp.said in (["The answer."], ["<ack>", "The answer."]), (delay, sp.said)


def test_turn_log_does_not_grow_without_bound():
    for i in range(1200):
        turnlog.record({"text": f"t{i}", "pad": "x" * 200})
    lines = turnlog._file().read_text().splitlines()
    assert len(lines) <= turnlog.KEEP * 2 and len(turnlog.recent(5)) == 5


def test_a_turn_publishes_routing_tools_and_the_spoken_lines_to_the_live_view():
    from hermes_jarvis.events import bus

    async def go():
        q = bus.subscribe()
        brain = FakeBrain([
            {"type": "session", "id": "s"},
            {"type": "tool", "tool": "terminal", "label": "ls ~/secret-project", "status": "running"},
            {"type": "tool", "tool": "terminal", "status": "completed"},
            {"type": "text", "delta": "<speak>The folder has two files.</speak>"},
            {"type": "done"},
        ])
        await conversation.Conversation(brain, FakeSpeaker(), FakeRouter(Route("work", "api-1", "jev-resume", router_ms=240))).handle("list it")
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        return events

    events = asyncio.run(go())
    kinds = [e["type"] for e in events]
    assert kinds.index("route") < kinds.index("tool") < kinds.index("transcript")
    route = next(e for e in events if e["type"] == "route")
    assert (route["profile"], route["reason"], route["router_ms"], route["resumed"]) == ("work", "jev-resume", 240, True)
    tools = [e for e in events if e["type"] == "tool"]
    assert [t["status"] for t in tools] == ["running", "completed"] and tools[0]["label"] == "ls ~/secret-project"
    said = next(e for e in events if e["type"] == "transcript")
    assert said["role"] == "assistant" and said["text"] == "The folder has two files."


def test_what_a_tool_touched_is_hidden_when_transcripts_are_off():
    from hermes_jarvis import config
    from hermes_jarvis.events import bus

    config.use({"privacy": {"save_transcripts": False}}, base_dir=config.cfg.base_dir)

    async def go():
        q = bus.subscribe()
        brain = FakeBrain([{"type": "session", "id": "s"},
                           {"type": "tool", "tool": "terminal", "label": "cat private.txt", "status": "running"},
                           {"type": "text", "delta": "<speak>Read it.</speak>"}, {"type": "done"}])
        await conversation.Conversation(brain, FakeSpeaker(), new_route()).handle("read it")
        return [q.get_nowait() for _ in range(q.qsize())]

    events = asyncio.run(go())
    assert all("private.txt" not in str(e) and "Read it" not in str(e) for e in events)
    assert next(e for e in events if e["type"] == "tool")["label"] == ""


def test_progress_line_is_spoken_while_the_brain_is_silent(tmp_path, monkeypatch):
    import asyncio

    from hermes_jarvis import conversation
    from hermes_jarvis.settings import settings

    monkeypatch.setattr(conversation, "STATE_FILE", tmp_path / "s.json")
    spoken = []

    class Sp:
        generation = 0
        canned = []

        async def say(self, text, gen=None):
            spoken.append(text)

        async def say_canned(self, gen=None):
            return None

    class Slow:
        supports_sessions = False

        async def turn(self, text, sid, profile):
            await asyncio.sleep(0.6)
            yield {"type": "text", "delta": "<speak>Done.</speak>"}

    class R:
        async def route(self, *a, **k):
            from hermes_jarvis.router import Route
            return Route("default", None, "disabled")

    settings.update({"progress_every_s": 0.2, "ack_after_s": 30})
    try:
        asyncio.run(conversation.Conversation(Slow(), Sp(), R()).handle("hello"))
    finally:
        settings.update({"progress_every_s": 15.0, "ack_after_s": 2.5})
    assert any("on it" in s.lower() or "nearly" in s.lower() or "bear" in s.lower() or "still" in s.lower()
               for s in spoken[:-1]) and spoken[-1] == "Done."
