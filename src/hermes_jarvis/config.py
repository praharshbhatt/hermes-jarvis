"""Startup configuration.

Sources, lowest to highest priority: built-in DEFAULTS, `config.yaml`, `HJ_<SECTION>_<KEY>` environment variables
(for example `HJ_ADMIN_HOST=0.0.0.0`). Secrets (API keys, passwords) are never read from config.yaml: they come from
the environment or a `.env` file next to the config file.

Tunables that people change while the assistant runs (speech speed, thresholds, prompts, profiles) are not here;
they live in settings.py and are edited from the admin UI.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import socket
from pathlib import Path
from types import SimpleNamespace

import yaml

from .errors import UserError

log = logging.getLogger("hermes_jarvis.config")

DEFAULTS: dict = {
    "data_dir": "./data",
    "persona": "jarvis",  # jarvis | neutral (see personas.py)
    "user": {
        "name": "",           # your name; only used in the persona text for openai brains
        "address_as": "sir",  # how canned lines address you: "sir", "ma'am", "boss", or "" for none
    },
    "device": {
        "host": "",  # empty: find the device on the network (mDNS), or use the one saved by `hermes-jarvis adopt`
        "port": 6053,
        "wake_word": "hey_jarvis",   # which of the device's wake words to activate when none is ("" = leave as is)
    },
    "audio": {
        "public_host": "",  # address the device uses to fetch speech clips; empty = detect
        "port": 8651,
    },
    "brain": {
        "type": "hermes",  # hermes | openai (any OpenAI-compatible chat completions endpoint)
        "base_url": "http://localhost:8642",
        "model": "hermes-agent",
        "api_key_env": "HERMES_API_KEY",
        "history_messages": 24,  # openai type only: how many past messages to resend
        "system_prompt": "",     # openai type only: persona text; empty = the persona preset's text
    },
    "stt": {
        "provider": "elevenlabs",  # elevenlabs | deepgram | openai | local
        "compare_with": "",        # optional second provider, run in parallel and only logged
        "language": "en",
        "local_model": "small.en",  # faster-whisper model for provider "local"
        "openai_model": "gpt-4o-mini-transcribe",
        "openai_base_url": "https://api.openai.com/v1",  # any server with /audio/transcriptions works (self-hosted Whisper)
    },
    "tts": {
        "voice": "en_GB-alan-medium",  # a name from `hermes-jarvis voices list`, or a path to a Piper .onnx file
    },
    "router": {
        "enabled": True,  # profile and conversation routing; needs OPENROUTER_API_KEY and a Hermes brain
    },
    "admin": {
        "host": "127.0.0.1",
        "port": 8650,
        "user": "admin",
        "session_idle_minutes": 30,   # a session ends after this long without activity
        "session_max_hours": 12,      # ... and never lasts longer than this
        "trust_proxy": False,         # believe X-Forwarded-Proto/Host from a reverse proxy you control (for https cookies)
        "allowed_origins": [],        # extra browser origins allowed to make changes, e.g. a dev server: http://localhost:3000
    },
    "privacy": {
        "save_recordings": False,     # keep what the microphone heard as WAV files in data/recordings
        "recordings_keep_days": 7,
        "save_transcripts": True,     # keep recent transcripts for the admin UI and tuning
    },
}


class Config(SimpleNamespace):
    """Nested namespace: cfg.device.host. Built from a dict by `_ns`."""

    path: Path | None = None
    base_dir: Path = Path(".")

    def data_path(self, *parts: str) -> Path:
        p = (self.base_dir / self.data_dir).resolve().joinpath(*parts)
        return p


def _ns(d: dict) -> SimpleNamespace:
    return Config(**{k: _ns(v) if isinstance(v, dict) else v for k, v in d.items()})


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif k in out:
            out[k] = v
        else:
            raise ValueError(f"unknown config key: {k}")
    return out


def _coerce(name: str, proto, raw: str):
    try:
        if isinstance(proto, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(proto, int):
            return int(raw)
        if isinstance(proto, float):
            return float(raw)
        if isinstance(proto, list):
            return [x.strip() for x in raw.split(",") if x.strip()]
    except ValueError as e:
        raise UserError(f"{name}={raw!r} is not a valid {type(proto).__name__}") from e
    return raw


def _apply_env(d: dict, prefix: str = "HJ", used: set | None = None) -> set:
    used = set() if used is None else used
    for k, v in d.items():
        name = f"{prefix}_{k.upper()}"
        if isinstance(v, dict):
            _apply_env(v, name, used)
        elif name in os.environ:
            d[k] = _coerce(name, v, os.environ[name])
            used.add(name)
    return used


def load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines. Existing environment variables win."""
    try:
        text = path.read_text()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def load(path: str | os.PathLike | None = None) -> Config:
    """Load config.yaml (path, $HERMES_JARVIS_CONFIG, or ./config.yaml), apply env overrides, set the global cfg."""
    global cfg
    explicit = path or os.environ.get("HERMES_JARVIS_CONFIG")
    p = Path(explicit or "config.yaml")
    if explicit and not p.exists():
        raise UserError(f"config file not found: {p}")
    raw: dict = {}
    if p.exists():
        try:
            raw = yaml.safe_load(p.read_text()) or {}
            merged = _merge(DEFAULTS, raw)
        except (yaml.YAMLError, ValueError, AttributeError) as e:
            raise UserError(f"{p}: {e}") from e
    else:
        merged = _merge(DEFAULTS, {})
    used = _apply_env(merged)
    stray = sorted(k for k in os.environ if k.startswith("HJ_") and k not in used)
    if stray:
        log.warning("ignoring environment variable(s) that are not settings: %s", ", ".join(stray))
    cfg = _ns(merged)
    cfg.path = p if p.exists() else None
    cfg.base_dir = p.resolve().parent
    load_dotenv(cfg.base_dir / ".env")
    return cfg


def use(overrides: dict | None = None, base_dir: str | os.PathLike = ".") -> Config:
    """Set the global config from a dict (tests, embedding). No files are read."""
    global cfg
    cfg = _ns(_merge(DEFAULTS, overrides or {}))
    cfg.path = None
    cfg.base_dir = Path(base_dir)
    return cfg


cfg: Config = use()


def shown(text: str) -> str:
    """Text for log lines: what was said and answered, or a placeholder when privacy.save_transcripts is off."""
    return text if cfg.privacy.save_transcripts else "<hidden>"


# ----- secrets and environment -----
def secret(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ----- the device this install talks to -----
def _device_file() -> Path:
    return cfg.data_path("device.json")


def saved_device() -> dict:
    """What `hermes-jarvis adopt` stored: {host, name, key}."""
    try:
        return json.loads(_device_file().read_text())
    except (OSError, ValueError):
        return {}


def save_device(info: dict) -> None:
    p = _device_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(info, indent=2))
    os.chmod(p, 0o600)


def device_key() -> str | None:
    """Base64 API encryption key of the device: $ESPHOME_API_KEY, else the one saved by adopt, else None."""
    return secret("ESPHOME_API_KEY") or saved_device().get("key") or None


def device_host() -> str:
    return cfg.device.host or saved_device().get("host", "")


def lan_ip(toward: str = "") -> str:
    """Our address as seen from the device (override with audio.public_host)."""
    if cfg.audio.public_host:
        return cfg.audio.public_host
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((toward or device_host() or "192.0.2.1", 6053))  # UDP connect sends nothing
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
