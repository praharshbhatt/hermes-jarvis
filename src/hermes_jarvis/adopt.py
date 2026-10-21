"""Adopt a device: give it a private API encryption key, the way Home Assistant does when it adds an ESPHome device.

The published firmware is built with key-less encryption: until a client sets a key it accepts a plaintext
connection, and once a key is set it only accepts that key (only a factory reset removes it). `adopt` generates a
random key, sends it to the device, reconnects with it to prove it works, and saves it to <data_dir>/device.json.
"""
from __future__ import annotations

import asyncio
import base64
import os

from aioesphomeapi import APIClient, InvalidEncryptionKeyAPIError, RequiresEncryptionAPIError

from . import config


class AdoptError(RuntimeError):
    pass


async def adopt(host: str, name: str = "", port: int = 6053) -> dict:
    # 1. plaintext connect: works only on a device that has no key yet
    probe = APIClient(host, port, None)
    try:
        await probe.connect(login=True)
    except RequiresEncryptionAPIError as e:
        existing = config.device_key()
        if not existing:
            raise AdoptError(
                f"{host} already has an encryption key (it was adopted by Home Assistant or another install). "
                "Set ESPHOME_API_KEY to its key, or factory-reset the device and flash again.") from e
        info = await _verify(host, port, existing)
        return _save(host, info, existing, note="already adopted; saved the key you provided")
    except Exception as e:
        raise AdoptError(f"could not connect to {host}:{port}: {e}") from e
    try:
        await probe.device_info()
        # 2. send a fresh key
        key = base64.b64encode(os.urandom(32)).decode()
        if not await probe.noise_encryption_set_key(key.encode()):
            raise AdoptError("the device refused the key (was it built with `api: encryption:`?)")
    finally:
        await probe.disconnect()
    # 3. reconnect with the key; the device needs a moment to switch over
    last: Exception | None = None
    for _ in range(10):
        await asyncio.sleep(1.5)
        try:
            info = await _verify(host, port, key)
            return _save(host, info, key, note="adopted")
        except Exception as e:  # device still switching over
            last = e
    raise AdoptError(f"the key was sent but the device did not accept it afterwards: {last}")


async def _verify(host: str, port: int, key: str):
    c = APIClient(host, port, None, noise_psk=key)
    try:
        await c.connect(login=True)
        return await c.device_info()
    except InvalidEncryptionKeyAPIError as e:
        raise AdoptError("that key does not match the device") from e
    finally:
        await c.disconnect()


def _save(host: str, info, key: str, note: str) -> dict:
    out = {"host": host, "name": info.name, "mac": info.mac_address, "key": key, "esphome": info.esphome_version,
           "note": note}
    config.save_device({k: v for k, v in out.items() if k != "note"})
    return out
