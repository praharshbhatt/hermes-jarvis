"""Recent spoken turns: a small in-memory ring plus a JSON-lines file, for the admin UI and for tuning.

With privacy.save_transcripts set to false the text of each turn is not kept; only timings and routing are.
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from . import config
from .util import trim_lines

FILE: Path | None = None  # tests may point this elsewhere
KEEP = 500  # lines kept on disk (the admin UI shows the latest 40)
_ring: deque = deque(maxlen=200)
_loaded_from: Path | None = None


def _file() -> Path:
    return FILE or config.cfg.data_path("turns.jsonl")


def _load() -> None:
    global _loaded_from
    f = _file()
    if _loaded_from == f:
        return
    _loaded_from = f
    _ring.clear()
    try:
        for line in f.read_text().splitlines()[-200:]:
            _ring.append(json.loads(line))
    except (OSError, ValueError):
        pass


def record(entry: dict) -> None:
    _load()
    entry = {"ts": time.time(), **entry}
    if not config.cfg.privacy.save_transcripts:
        entry["text"] = ""
    _ring.append(entry)
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    trim_lines(f, KEEP)


def recent(limit: int = 30) -> list[dict]:
    _load()
    return list(_ring)[-limit:][::-1]
