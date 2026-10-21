import json

import pytest

from hermes_jarvis import config, personas
from hermes_jarvis.settings import settings


def test_defaults_are_generic():
    s = settings.all()
    assert [p["name"] for p in s["profiles"]] == ["default"]       # one profile, no one's setup
    blob = json.dumps(s)
    assert "192.168." not in blob and "/home/" not in blob          # no addresses or paths


def test_update_persists_and_is_logged():
    assert settings.update({"recent_sessions_count": 7}) == ["recent_sessions_count"]
    assert settings.get("recent_sessions_count") == 7
    assert settings.update({"recent_sessions_count": 7}) == []  # no change, no history entry
    h = settings.history()
    assert len(h) == 1 and h[0]["key"] == "recent_sessions_count" and h[0]["new"] == 7
    assert json.loads(config.cfg.data_path("settings.json").read_text()) == {"recent_sessions_count": 7}


def test_unknown_keys_are_rejected():
    with pytest.raises(ValueError, match="unknown setting"):
        settings.update({"nope": 1})


def test_a_file_edited_on_disk_is_picked_up_without_a_restart():
    settings.update({"ack_after_s": 3.0})
    f = config.cfg.data_path("settings.json")
    f.write_text(json.dumps({"ack_after_s": 9.5}))
    assert settings.get("ack_after_s") == 9.5


def test_list_settings_accept_multiline_text():
    settings.update({"canned_acks": "One.\n\n Two. \nThree."})
    assert settings.get("canned_acks") == ["One.", "Two.", "Three."]


def test_profile_rules():
    ok = [{"name": "default", "is_default": True, "enabled": True, "description": ""},
          {"name": "Work", "is_default": False, "enabled": True, "description": "clients"}]
    settings.update({"profiles": ok})
    assert [p["name"] for p in settings.get("profiles")] == ["default", "work"]  # names are lower-cased
    bad = [
        [],
        [{"name": "a", "is_default": True}, {"name": "b", "is_default": True}],      # two defaults
        [{"name": "a", "is_default": False}],                                        # no default
        [{"name": "bad name!", "is_default": True}],                                 # not a slug
        [{"name": "a", "is_default": True}, {"name": "a", "is_default": False}],     # duplicate
        [{"name": "a", "is_default": True, "enabled": False}],                       # default disabled
    ]
    for profiles in bad:
        with pytest.raises(ValueError):
            settings.update({"profiles": profiles})


def test_acks_fill_the_address():
    config.use({"persona": "jarvis", "user": {"address_as": "boss"}, "data_dir": str(config.cfg.data_path())})
    acks = settings.acks()
    assert "On it, boss." in acks and not any("{address}" in a for a in acks)
    settings.update({"address_as": ""})
    acks = settings.acks()
    assert "On it." in acks and not any("{address}" in a or ", ." in a for a in acks)


def test_persona_render_and_presets():
    assert personas.render("Right away, {address}.", "ma'am") == "Right away, ma'am."
    assert personas.render("Right away, {address}.", "") == "Right away."
    assert personas.get("does-not-exist") is personas.PERSONAS["neutral"]
    assert all("{address}" not in a for a in personas.PERSONAS["neutral"]["acks"])


def test_numbers_are_range_checked():
    import math
    for key, bad in [("piper_length_scale", 0), ("piper_length_scale", -1), ("vad_silence_s", 0),
                     ("session_threshold", 1.5), ("ack_after_s", math.nan), ("no_speech_s", math.inf),
                     ("recent_sessions_count", 0), ("piper_length_scale", "fast")]:
        with pytest.raises(ValueError):
            settings.update({key: bad})
    assert settings.update({"piper_length_scale": 1.2, "recent_sessions_count": "7"}) == [
        "piper_length_scale", "recent_sessions_count"]
    assert settings.get("recent_sessions_count") == 7 and isinstance(settings.get("recent_sessions_count"), int)


def test_history_does_not_grow_without_bound():
    from hermes_jarvis import settings as m
    for i in range(1300):
        settings.update({"ack_after_s": float(i % 20 + 1) + (0.5 if i % 2 else 0)})
    lines = config.cfg.data_path("settings-history.jsonl").read_text().splitlines()
    assert len(lines) <= m.HISTORY_KEEP * 2
