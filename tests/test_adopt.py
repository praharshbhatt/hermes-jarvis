"""The adoption flow against a fake ESPHome client: first adoption, an already-adopted device, wrong keys."""
import asyncio

import pytest
from aioesphomeapi import InvalidEncryptionKeyAPIError, RequiresEncryptionAPIError

from hermes_jarvis import adopt as adopt_mod
from hermes_jarvis import config


class FakeInfo:
    name, mac_address, esphome_version = "voice-1", "AA:BB", "2025.7.2"


class FakeClient:
    """A device. `keyless` devices accept plaintext until a key is set; then only that key."""
    device = {"key": None, "set_ok": True, "settle_after": 0}
    attempts = 0

    def __init__(self, host, port, password, noise_psk=None):
        self.noise_psk = noise_psk

    async def connect(self, login=False, **_):
        d = FakeClient.device
        if d["key"] is not None:
            if self.noise_psk is None:
                raise RequiresEncryptionAPIError("Connection requires encryption")
            if self.noise_psk != d["key"]:
                raise InvalidEncryptionKeyAPIError("bad key")
            FakeClient.attempts += 1
            if FakeClient.attempts <= d["settle_after"]:
                raise OSError("still rebooting")

    async def device_info(self):
        return FakeInfo()

    async def noise_encryption_set_key(self, key: bytes):
        if not FakeClient.device["set_ok"]:
            return False
        FakeClient.device["key"] = key.decode()
        return True

    async def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeClient.device = {"key": None, "set_ok": True, "settle_after": 0}
    FakeClient.attempts = 0
    monkeypatch.setattr(adopt_mod, "APIClient", FakeClient)

    async def no_sleep(_):
        pass
    monkeypatch.setattr(adopt_mod.asyncio, "sleep", no_sleep)


def run(coro):
    return asyncio.run(coro)


def test_a_new_device_gets_a_random_key_and_it_is_saved_privately():
    out = run(adopt_mod.adopt("10.0.0.5"))
    key = FakeClient.device["key"]
    assert out["note"] == "adopted" and len(__import__("base64").b64decode(key)) == 32
    saved = config.saved_device()
    assert saved == {"host": "10.0.0.5", "name": "voice-1", "mac": "AA:BB", "key": key, "esphome": "2025.7.2"}
    assert oct(config.cfg.data_path("device.json").stat().st_mode & 0o777) == "0o600"
    assert config.device_key() == key


def test_two_devices_get_different_keys():
    run(adopt_mod.adopt("a"))
    first = FakeClient.device["key"]
    FakeClient.device["key"] = None
    run(adopt_mod.adopt("b"))
    assert FakeClient.device["key"] != first


def test_an_already_adopted_device_needs_its_key():
    FakeClient.device["key"] = "someone-elses-key"
    with pytest.raises(adopt_mod.AdoptError, match="already has an encryption key"):
        run(adopt_mod.adopt("10.0.0.5"))
    assert config.saved_device() == {}


def test_an_already_adopted_device_with_the_right_key_is_saved(monkeypatch):
    FakeClient.device["key"] = "the-key"
    monkeypatch.setenv("ESPHOME_API_KEY", "the-key")
    out = run(adopt_mod.adopt("10.0.0.5"))
    assert "already adopted" in out["note"] and config.saved_device()["key"] == "the-key"


def test_the_wrong_key_for_an_adopted_device_is_explained(monkeypatch):
    FakeClient.device["key"] = "the-key"
    monkeypatch.setenv("ESPHOME_API_KEY", "wrong")
    with pytest.raises(adopt_mod.AdoptError, match="does not match"):
        run(adopt_mod.adopt("10.0.0.5"))


def test_a_device_that_refuses_the_key_is_reported():
    FakeClient.device["set_ok"] = False
    with pytest.raises(adopt_mod.AdoptError, match="refused the key"):
        run(adopt_mod.adopt("10.0.0.5"))


def test_a_device_that_is_slow_to_switch_over_is_waited_for():
    FakeClient.device["settle_after"] = 3
    assert run(adopt_mod.adopt("10.0.0.5"))["note"] == "adopted"
