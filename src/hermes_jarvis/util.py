"""Small helpers shared by several modules."""
from __future__ import annotations

from pathlib import Path


def trim_lines(path: Path, keep: int) -> None:
    """Keep a log file from growing forever: when it holds more than 2x `keep` lines, rewrite it with the last `keep`."""
    try:
        if path.stat().st_size < keep * 60:  # cheap check first: lines are rarely shorter than this
            return
        lines = path.read_text().splitlines()
        if len(lines) > keep * 2:
            path.write_text("\n".join(lines[-keep:]) + "\n")
    except OSError:
        pass
