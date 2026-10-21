"""Read and change the device's own controls (wake word sensitivity, mute, wake sound, ...) and read its log.

This is what Home Assistant's device page would normally be used for. Used by `hermes-jarvis device ...` and by the
admin UI's Device card.
"""
from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager

from aioesphomeapi import APIClient, ButtonInfo, LogLevel, NumberInfo, SelectInfo, SwitchInfo

from . import config, discovery

CONTROLS = (SelectInfo, SwitchInfo, NumberInfo, ButtonInfo)


def kind(e) -> str:
    return {SelectInfo: "select", SwitchInfo: "switch", NumberInfo: "number", ButtonInfo: "button"}[type(e)]


def describe(ents, states: dict) -> list[dict]:
    """The controllable entities with their current state, for display."""
    out = []
    for e in ents:
        if not isinstance(e, CONTROLS):
            continue
        item = {"name": e.name, "id": e.object_id, "kind": kind(e), "state": None}
        st = states.get(e.key)
        if st is not None and hasattr(st, "state") and not getattr(st, "missing_state", False):
            item["state"] = st.state
        if isinstance(e, SelectInfo):
            item["options"] = list(e.options)
        if isinstance(e, NumberInfo):
            item.update(min=e.min_value, max=e.max_value, step=e.step)
        out.append(item)
    return out


def find(ents, name: str):
    want = name.strip().casefold()
    for e in ents:
        if isinstance(e, CONTROLS) and want in (e.name.casefold(), e.object_id.casefold()):
            return e
    raise ValueError(f"no control named {name!r}")


def apply(client: APIClient, ents, name: str, value=None) -> str:
    """Change one control. Raises ValueError for an unknown name or a value the control does not accept."""
    e = find(ents, name)
    if isinstance(e, SelectInfo):
        match = next((o for o in e.options if o.casefold() == str(value).casefold()), None)
        if match is None:
            raise ValueError(f"{e.name}: choose one of {', '.join(e.options)}")
        client.select_command(e.key, match)
        return f"{e.name} = {match}"
    if isinstance(e, SwitchInfo):
        on = str(value).strip().lower() in ("1", "true", "on", "yes")
        if str(value).strip().lower() not in ("1", "true", "on", "yes", "0", "false", "off", "no"):
            raise ValueError(f"{e.name}: use on or off")
        client.switch_command(e.key, on)
        return f"{e.name} = {'on' if on else 'off'}"
    if isinstance(e, NumberInfo):
        v = float(value)
        if not e.min_value <= v <= e.max_value:
            raise ValueError(f"{e.name}: between {e.min_value} and {e.max_value}")
        client.number_command(e.key, v)
        return f"{e.name} = {v}"
    client.button_command(e.key)
    return f"pressed {e.name}"


@asynccontextmanager
async def connected():
    """A short-lived connection to the device, for the command line."""
    host, _ = await discovery.resolve_host()
    if not host:
        raise RuntimeError("no device found (run `hermes-jarvis adopt`, or set device.host)")
    c = APIClient(host, int(config.cfg.device.port), None, noise_psk=config.device_key())
    await c.connect(login=True)
    try:
        yield c
    finally:
        await c.disconnect()


async def snapshot(c: APIClient, wait: float = 1.5):
    """Entities and their current states (the device sends states right after we subscribe)."""
    ents, _ = await c.list_entities_services()
    states: dict = {}
    c.subscribe_states(lambda st: states.__setitem__(st.key, st))
    await asyncio.sleep(wait)
    return ents, states


async def stream_logs(c: APIClient, seconds: float, out=print) -> None:
    ansi = re.compile(r"\x1b\[[0-9;]*m")  # the device colours its log lines
    c.subscribe_logs(lambda m: out(ansi.sub("", m.message.decode("utf-8", "replace")).rstrip()),
                     log_level=LogLevel.LOG_LEVEL_DEBUG)
    await asyncio.sleep(seconds)
