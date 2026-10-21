"""Device controls: listing, finding by name, and applying values with validation."""
from types import SimpleNamespace

import pytest
from aioesphomeapi import ButtonInfo, NumberInfo, SelectInfo, SensorInfo, SwitchInfo

from hermes_jarvis import devicectl


class FakeClient:
    def __init__(self):
        self.calls = []

    def select_command(self, key, v): self.calls.append(("select", key, v))
    def switch_command(self, key, v): self.calls.append(("switch", key, v))
    def number_command(self, key, v): self.calls.append(("number", key, v))
    def button_command(self, key): self.calls.append(("button", key))


ENTS = [
    SelectInfo(key=1, object_id="wake_word_sensitivity", name="Wake word sensitivity",
               options=["Slightly sensitive", "Very sensitive"]),
    SwitchInfo(key=2, object_id="mute", name="Mute"),
    NumberInfo(key=3, object_id="volume", name="Volume", min_value=0.0, max_value=1.0, step=0.1),
    ButtonInfo(key=4, object_id="restart", name="Restart"),
    SensorInfo(key=5, object_id="temp", name="Temperature"),   # not controllable: never listed
]


def test_describe_lists_only_controls_with_state():
    states = {1: SimpleNamespace(state="Very sensitive", missing_state=False), 2: SimpleNamespace(state=True, missing_state=False)}
    items = {i["id"]: i for i in devicectl.describe(ENTS, states)}
    assert set(items) == {"wake_word_sensitivity", "mute", "volume", "restart"}
    assert items["wake_word_sensitivity"]["state"] == "Very sensitive" and "Slightly sensitive" in items["wake_word_sensitivity"]["options"]
    assert items["mute"]["state"] is True and items["volume"]["max"] == 1.0 and items["volume"]["state"] is None


def test_apply_validates_and_sends():
    c = FakeClient()
    assert devicectl.apply(c, ENTS, "wake word sensitivity", "slightly SENSITIVE") == "Wake word sensitivity = Slightly sensitive"
    assert devicectl.apply(c, ENTS, "mute", "on") == "Mute = on"
    assert devicectl.apply(c, ENTS, "volume", "0.5") == "Volume = 0.5"
    assert devicectl.apply(c, ENTS, "Restart") == "pressed Restart"
    assert c.calls == [("select", 1, "Slightly sensitive"), ("switch", 2, True), ("number", 3, 0.5), ("button", 4)]
    for name, value in [("wake_word_sensitivity", "loud"), ("mute", "maybe"), ("volume", "7"), ("nothing", "x"), ("temp", "1")]:
        with pytest.raises(ValueError):
            devicectl.apply(c, ENTS, name, value)
    assert len(c.calls) == 4  # nothing invalid was sent
