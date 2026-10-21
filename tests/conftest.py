"""Shared fixtures. Every test runs against a temporary data directory and a fresh config, so nothing touches real
settings, and no test needs a device, a model, or the network."""
import pytest

from hermes_jarvis import config, conversation, turnlog
from hermes_jarvis import settings as settings_mod
from hermes_jarvis.events import bus


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for var in [v for v in __import__("os").environ if v.startswith("HJ_")]:
        monkeypatch.delenv(var, raising=False)
    for var in ("HERMES_API_KEY", "OPENROUTER_API_KEY", "ADMIN_PASSWORD", "ADMIN_PASSWORD_HASH", "ESPHOME_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    config.use({"data_dir": str(tmp_path / "data")}, base_dir=tmp_path)
    monkeypatch.setattr(conversation, "STATE_FILE", None)
    monkeypatch.setattr(turnlog, "FILE", None)
    monkeypatch.setattr(turnlog, "_loaded_from", None)
    settings_mod.settings._data, settings_mod.settings._sig = {}, None
    bus._subs.clear()
    bus._recent.clear()
    bus.state, bus.device_connected, bus.device_name = "idle", False, ""
    yield tmp_path
