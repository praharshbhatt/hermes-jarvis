from hermes_jarvis.discovery import Device
from hermes_jarvis.vad import CHUNK_BYTES, Endpointer


def test_endpointer_gives_up_on_silence():
    ep = Endpointer(no_speech_s=0.3)
    events = []
    for _ in range(40):
        events += ep.feed(b"\0" * CHUNK_BYTES)
    assert events == ["no_speech"]


def test_endpointer_thresholds_can_change_per_utterance():
    ep = Endpointer()
    ep.reset(silence_s=0.4, no_speech_s=2.0)
    assert ep.silence_chunks == int(0.4 / 0.032) and ep.no_speech_chunks == int(2.0 / 0.032)


def test_voice_devices_are_recognised_by_name_or_project():
    assert Device("home-assistant-voice-a1b2c3", "1.2.3.4", 6053).likely_voice
    assert Device("kitchen", "1.2.3.4", 6053, project="Nabu Casa.Home Assistant Voice PE").likely_voice
    assert not Device("garage-door", "1.2.3.4", 6053).likely_voice
