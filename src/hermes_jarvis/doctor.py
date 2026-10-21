"""`hermes-jarvis doctor`: check the setup and say what to fix, in plain words."""
from __future__ import annotations

import socket
import sys

from aioesphomeapi import (
    APIClient,
    EventInfo,
    InvalidEncryptionKeyAPIError,
    MediaPlayerInfo,
    RequiresEncryptionAPIError,
    VoiceAssistantFeature,
)

from . import config, discovery
from .brains import make_brain
from .settings import settings
from .stt import STT
from .tts import voices

OK, WARN, FAIL = "ok", "warn", "FAIL"
_COLORS = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}


def _line(level: str, label: str, detail: str = "") -> str:
    tag = f"{level:>4}"
    if sys.stdout.isatty():
        tag = f"{_COLORS[level]}{tag}\033[0m"
    return f"  {tag}  {label}" + (f": {detail}" if detail else "")


async def collect(printer=None, running: bool = False) -> list[tuple[str, str, str]]:
    """Run every check. Returns (level, label, detail) rows; `printer`, if given, is called with each formatted line as it
    is produced. `running=True` means the bridge itself is the caller, so its own port being busy is expected."""
    results: list[tuple[str, str, str]] = []

    def add(level: str, label: str, detail: str = "") -> None:
        results.append((level, label, detail))
        if printer:
            printer(_line(level, label, detail))

    c = config.cfg
    add(OK if c.path else WARN, "config file", str(c.path) if c.path else "none found, using defaults (run `hermes-jarvis init`)")
    try:
        d = c.data_path()
        d.mkdir(parents=True, exist_ok=True)
        (d / ".write-test").write_text("x")
        (d / ".write-test").unlink()
        add(OK, "data directory writable", str(d))
    except OSError as e:
        add(FAIL, "data directory writable", f"{c.data_path()}: {e}")

    add(OK if config.secret("ADMIN_PASSWORD") else WARN, "admin UI password",
        "set" if config.secret("ADMIN_PASSWORD") else "ADMIN_PASSWORD is not set, so the admin UI is off")

    # voice
    v = c.tts.voice
    if voices.installed(v):
        add(OK, "speech voice", f"{v} installed")
    elif v in voices.CATALOG:
        add(WARN, "speech voice", f"{v} is not downloaded yet; it will download on first start (or run `hermes-jarvis voices download {v}`)")
    elif v.endswith(".onnx"):
        add(FAIL, "speech voice", f"file not found: {voices.model_path(v)} (and its .json)")
    else:
        add(FAIL, "speech voice", f"unknown voice {v!r}; see `hermes-jarvis voices list`")

    # speech to text
    try:
        for p in STT().providers():
            ok, detail = p.check()
            add(OK if ok else FAIL, f"speech to text ({p.name})", detail)
    except ValueError as e:
        add(FAIL, "speech to text", str(e))

    # brain
    brain = None
    try:
        brain = make_brain()
        for label, ok, detail in await brain.check():
            add(OK if ok else FAIL, label, detail)
        if brain.supports_sessions:
            if not config.secret("OPENROUTER_API_KEY"):
                add(WARN, "router", "OPENROUTER_API_KEY not set: conversations are not matched across sessions "
                                    "(optional; see docs/configuration.md)")
            elif settings.get("router_enabled"):
                add(OK, "router", "OpenRouter key set")
    except ValueError as e:
        add(FAIL, "brain", str(e))
    finally:
        if brain:
            await brain.close()

    # the device
    try:
        host, name = await discovery.resolve_host()
    except Exception as e:
        host, name = "", ""
        add(WARN, "device discovery", f"{type(e).__name__}: {e}")
    if not host:
        add(FAIL, "voice device", "none found. Power it on and run `hermes-jarvis adopt`, or set device.host in config.yaml")
    else:
        add(OK, "voice device address", f"{host}" + (f" ({name})" if name else ""))
        cli = APIClient(host, int(c.device.port), None, noise_psk=config.device_key())
        try:
            await cli.connect(login=True)
            info = await cli.device_info()
            ents, _ = await cli.list_entities_services()
            add(OK, "device connection", f"{info.name}, ESPHome {info.esphome_version}")
            if not config.device_key():
                add(WARN, "device encryption", "no key yet: the device is accepting unencrypted connections. "
                                               "Run `hermes-jarvis adopt` to lock it to a private key")
            flags = info.voice_assistant_feature_flags
            for feat, label, required in (
                (VoiceAssistantFeature.VOICE_ASSISTANT, "voice assistant", True),
                (VoiceAssistantFeature.API_AUDIO, "microphone audio over the API", True),
                (VoiceAssistantFeature.ANNOUNCE, "announcements (how replies are played)", True),
                (VoiceAssistantFeature.START_CONVERSATION, "listening again after a question", False),
            ):
                have = bool(flags & feat)
                add(OK if have else (FAIL if required else WARN), f"device supports {label}",
                    "" if have else "not offered by this firmware" + ("" if required else " (follow-up listening will not work)"))
            add(OK if any(isinstance(e, MediaPlayerInfo) for e in ents) else FAIL, "device has a speaker (media player)")
            has_stop = any(isinstance(e, EventInfo) and e.object_id == "stop_word" for e in ents)
            add(OK if has_stop else WARN, "stop word support",
                "present" if has_stop else "firmware lacks the 'Stop word' event; saying stop will not clear queued speech "
                                           "(flash the hermes-jarvis firmware)")
        except RequiresEncryptionAPIError:
            add(FAIL, "device connection", "the device has an encryption key we do not have. Run `hermes-jarvis adopt` "
                                           "(new device) or set ESPHOME_API_KEY")
        except InvalidEncryptionKeyAPIError:
            add(FAIL, "device connection", "the saved encryption key does not match the device (re-flashed or factory reset?). "
                                           "Run `hermes-jarvis adopt`")
        except Exception as e:
            add(FAIL, "device connection", f"{type(e).__name__}: {e}")
        finally:
            await cli.disconnect()

    # the path back: the device downloads speech clips from us
    ip = config.lan_ip(host)
    add(WARN if ip.startswith("127.") else OK, "address the device fetches speech from",
        f"http://{ip}:{c.audio.port}" + ("  (loopback: set audio.public_host, the device cannot reach this)" if ip.startswith("127.") else ""))
    s = socket.socket()
    s.settimeout(0.5)
    try:
        busy = s.connect_ex(("127.0.0.1", int(c.audio.port))) == 0
    finally:
        s.close()
    if busy and not running:
        add(WARN, "speech port", f"{c.audio.port} is already in use (is hermes-jarvis already running?)")
    return results


async def run() -> int:
    print("hermes-jarvis doctor\n")
    results = await collect(lambda line: print(line, flush=True))
    fails = sum(1 for r in results if r[0] == FAIL)
    warns = sum(1 for r in results if r[0] == WARN)
    print(f"\n{'All good.' if not fails else str(fails) + ' problem(s) to fix.'}" + (f" {warns} warning(s)." if warns else ""))
    return 1 if fails else 0
