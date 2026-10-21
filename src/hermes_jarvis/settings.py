"""Runtime settings, editable from the admin UI and applied without a restart.

Precedence: <data_dir>/settings.json (written by the UI) > DEFAULTS below. Startup configuration (device, ports,
providers) is in config.yaml and is not editable here. Secrets are never stored here.
Every change is appended to <data_dir>/settings-history.jsonl so a bad edit can be found and undone.
"""
from __future__ import annotations

import copy
import json
import math
import os
import threading
import time
from pathlib import Path

from . import config, personas, prompts
from .util import trim_lines

DEFAULT_PROFILES = [
    {"name": "default", "is_default": True, "enabled": True,
     "description": "General requests and anything that does not clearly belong to another profile."},
]


def _defaults() -> dict:
    cfg = config.cfg
    return {
        # session routing
        "session_window_minutes": 5.0,
        "recent_sessions_count": 10,
        "match_sources": ["api_server"],  # only sessions the API created are safe to continue (others may 409)
        "router_enabled": bool(cfg.router.enabled),
        # The router asks a small decision model (TypeSafe's Jev, through OpenRouter's experimental decisions API).
        "router_model": "typesafe/jev-1.14",
        "router_url": "https://openrouter.ai/api/alpha/decisions",
        "router_timeout_s": 3.0,
        "profile_threshold": 0.6,
        "session_threshold": 0.75,
        "router_profile_instructions": "Pick the Hermes profile that should handle the user's spoken request. "
                                       "Choose the default profile when the request is general or unclear.",
        "router_session_instructions": "Does the user's request continue one of these earlier conversations, "
                                       "or is it a new topic? Choose new unless one of them clearly matches.",
        # listening
        "vad_silence_s": 0.8,            # quiet time that ends an utterance
        "no_speech_s": 6.0,              # how long to wait for the first word after the wake word
        "followup_no_speech_s": 8.0,     # same, when the device started listening by itself after a question
        # follow-up questions: listen again by itself after the assistant asks a question
        "followup_enabled": True,
        "followup_window_minutes": 5.0,  # only if the user's request was this recent (late job results just speak)
        "followup_ignore_phrases": ["anything else"],  # closing questions that do not need an answer
        # voice
        "tts_voice": cfg.tts.voice,      # changed live from the admin UI (config.yaml's tts.voice is only the first default)
        "address_as": cfg.user.address_as,
        "piper_length_scale": 1.0,       # bigger = slower
        "piper_noise_scale": 0.667,
        "piper_noise_w_scale": 0.8,
        "ack_after_s": 2.5,
        "progress_every_s": 15.0,        # a long tool-using turn says "still working" this often while silent (0 = never)
        "canned_acks": list(personas.get(cfg.persona)["acks"]),  # {address} is filled from address_as
        "voice_prompt": prompts.VOICE_PROMPT,
        # profiles (Hermes brain only)
        "profiles": copy.deepcopy(DEFAULT_PROFILES),
        # first-run guide in the admin UI
        "onboarding_completed": False,
    }


# (low, high) for numeric settings. Out-of-range values (0, negative, NaN) can hang or crash the audio pipeline.
RANGES: dict[str, tuple[float, float]] = {
    "session_window_minutes": (0, 1440), "recent_sessions_count": (1, 50), "router_timeout_s": (0.5, 30),
    "profile_threshold": (0, 1), "session_threshold": (0, 1), "vad_silence_s": (0.2, 5), "no_speech_s": (1, 60),
    "followup_no_speech_s": (1, 60), "followup_window_minutes": (0, 1440), "piper_length_scale": (0.3, 3),
    "piper_noise_scale": (0, 2), "piper_noise_w_scale": (0, 2), "ack_after_s": (0, 30), "progress_every_s": (0, 300),
}
HISTORY_KEEP = 500
MAX_TEXT = 20000  # longest prompt or text setting


class Settings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {}
        self._sig: tuple | None = None          # (path, mtime_ns, size) of the file we last read


    # paths follow the active config, so tests and `config.load()` can move them
    def _file(self) -> Path:
        return config.cfg.data_path("settings.json")

    def _history(self) -> Path:
        return config.cfg.data_path("settings-history.jsonl")

    def _fresh(self) -> None:
        f = self._file()
        try:
            st = f.stat()
        except OSError:
            self._data, self._sig = {}, None
            return
        sig = (f, st.st_mtime_ns, st.st_size)  # size too: two quick writes can share a timestamp
        if sig != self._sig:
            try:
                self._data = json.loads(f.read_text())
            except (OSError, ValueError):
                self._data = {}
            self._sig = sig

    def get(self, key: str):
        with self._lock:
            self._fresh()
            return copy.deepcopy(self._data.get(key, _defaults()[key]))

    def all(self) -> dict:
        with self._lock:
            self._fresh()
            return {k: copy.deepcopy(self._data.get(k, v)) for k, v in _defaults().items()}

    def update(self, changes: dict, who: str = "admin") -> list[str]:
        """Validate and save. Returns the keys that actually changed."""
        defaults = _defaults()
        clean: dict = {}
        for key, val in changes.items():
            if key not in defaults:
                raise ValueError(f"unknown setting: {key}")
            clean[key] = _coerce(key, val, defaults[key])
        with self._lock:
            self._fresh()
            changed = []
            for key, val in clean.items():
                old = self._data.get(key, defaults[key])
                if old != val:
                    changed.append(key)
                    hist = self._history()
                    hist.parent.mkdir(parents=True, exist_ok=True)
                    with hist.open("a") as h:
                        h.write(json.dumps({"ts": time.time(), "who": who, "key": key, "old": old, "new": val}) + "\n")
                    trim_lines(hist, HISTORY_KEEP)
                    self._data[key] = val
            if changed:
                f = self._file()
                f.parent.mkdir(parents=True, exist_ok=True)
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._data, indent=2))
                os.replace(tmp, f)
                st = f.stat()
                self._sig = (f, st.st_mtime_ns, st.st_size)
            return changed

    def history(self, limit: int = 30) -> list[dict]:
        try:
            lines = self._history().read_text().splitlines()[-limit:]
        except OSError:
            return []
        return [json.loads(line) for line in reversed(lines)]

    def acks(self) -> list[str]:
        """Canned acknowledgements with {address} filled in."""
        addr = self.get("address_as")
        return [personas.render(a, addr) for a in self.get("canned_acks")]


def _coerce(key: str, val, proto):
    if key == "profiles":
        return _clean_profiles(val)
    if isinstance(proto, bool):
        return bool(val)
    if isinstance(proto, (int, float)):
        try:
            num = float(val)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{key}: {val!r} is not a number") from e
        if not math.isfinite(num):
            raise ValueError(f"{key}: must be a finite number")
        lo, hi = RANGES.get(key, (-math.inf, math.inf))
        if not lo <= num <= hi:
            raise ValueError(f"{key}: must be between {lo:g} and {hi:g}")
        return int(num) if isinstance(proto, int) else num
    if isinstance(proto, list):
        if isinstance(val, str):
            val = [x.strip() for x in val.splitlines() if x.strip()]
        if len(val) > 200 or any(len(str(x)) > 500 for x in val):
            raise ValueError(f"{key}: too many or too long entries")
        return [str(x) for x in val]
    text = str(val)
    if len(text) > MAX_TEXT:
        raise ValueError(f"{key}: longer than {MAX_TEXT} characters")
    return text


def _clean_profiles(profiles) -> list[dict]:
    out, seen = [], set()
    for p in profiles:
        name = str(p["name"]).strip().lower()
        if not name or not name.replace("-", "").replace("_", "").isalnum() or name in seen:
            raise ValueError(f"bad or duplicate profile name: {p.get('name')!r}")
        seen.add(name)
        out.append({"name": name, "description": str(p.get("description", "")).strip(),
                    "enabled": bool(p.get("enabled", True)), "is_default": bool(p.get("is_default", False))})
    if not out:
        raise ValueError("at least one profile is required")
    defaults = [p for p in out if p["is_default"]]
    if len(defaults) != 1:
        raise ValueError("exactly one profile must be the default")
    if not defaults[0]["enabled"]:
        raise ValueError("the default profile cannot be disabled")
    return out


settings = Settings()
