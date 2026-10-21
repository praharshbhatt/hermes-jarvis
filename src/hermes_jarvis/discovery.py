"""Find ESPHome devices on the network (mDNS), and decide which one this install should talk to."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from . import config

log = logging.getLogger("hermes_jarvis.discovery")
SERVICE = "_esphomelib._tcp.local."


@dataclass
class Device:
    name: str
    host: str
    port: int
    mac: str = ""
    version: str = ""
    project: str = ""
    adopted: bool = False      # already locked to an encryption key
    adoptable: bool = False    # can take a key from us (built with key-less encryption)

    @property
    def likely_voice(self) -> bool:
        s = f"{self.name} {self.project}".lower()
        return any(w in s for w in ("voice", "satellite", "assist", "jarvis", "echo"))


def _prop(props: dict, key: str) -> str:
    v = props.get(key.encode())
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else (v or "")


async def discover(timeout: float = 4.0) -> list[Device]:
    azc = AsyncZeroconf()
    names: set[str] = set()

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added:
            names.add(name)

    browser = AsyncServiceBrowser(azc.zeroconf, SERVICE, handlers=[on_change])
    try:
        await asyncio.sleep(timeout)

        async def resolve(n: str) -> Device | None:
            info = AsyncServiceInfo(SERVICE, n)
            if not await info.async_request(azc.zeroconf, 3000):
                return None
            addrs = info.parsed_addresses(IPVersion.V4Only)
            if not addrs:
                return None
            p = info.properties
            return Device(name=n.removesuffix("." + SERVICE), host=addrs[0], port=info.port or 6053,
                          mac=_prop(p, "mac"), version=_prop(p, "version"), project=_prop(p, "project_name"),
                          adopted=b"api_encryption" in p, adoptable=b"api_encryption_supported" in p)

        found = [d for d in await asyncio.gather(*(resolve(n) for n in names)) if d]
    finally:
        await browser.async_cancel()
        await azc.async_close()
    return sorted(found, key=lambda d: (not d.likely_voice, d.name))


async def resolve_host() -> tuple[str, str]:
    """Where to connect: (host, device name). Order: config device.host, the saved device (looked up by name so a
    changed IP address is followed), the saved IP, a single voice-like device on the network. ("", "") if none."""
    if config.cfg.device.host:
        return config.cfg.device.host, ""
    saved = config.saved_device()
    if saved.get("name"):
        for d in await discover(timeout=3.0):
            if d.name == saved["name"]:
                if d.host != saved.get("host"):
                    log.info("device %s moved from %s to %s", d.name, saved.get("host"), d.host)
                return d.host, d.name
    if saved.get("host"):
        return saved["host"], saved.get("name", "")
    voice = [d for d in await discover(timeout=4.0) if d.likely_voice]
    if len(voice) == 1:
        return voice[0].host, voice[0].name
    if len(voice) > 1:
        log.warning("several voice devices found (%s): set device.host in config.yaml or run `hermes-jarvis adopt`",
                    ", ".join(d.name for d in voice))
    return "", ""
