"""Piper voices: a small catalog, and download on demand from the upstream rhasspy/piper-voices repository.

Voices are never bundled with this project. Each voice has its own license (see its MODEL_CARD in the upstream
repository); you download it straight from there. A voice can also be a path to any Piper .onnx file you already have.
"""
from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

from .. import config

log = logging.getLogger("hermes_jarvis.tts")
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# name -> (path in the upstream repo without extension, description)
CATALOG: dict[str, tuple[str, str]] = {
    "en_GB-alan-medium": ("en/en_GB/alan/medium/en_GB-alan-medium", "British English, male (default)"),
    "en_GB-northern_english_male-medium": ("en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium",
                                           "Northern English, male"),
    "en_GB-alba-medium": ("en/en_GB/alba/medium/en_GB-alba-medium", "Scottish English, female"),
    "en_GB-jenny_dioco-medium": ("en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium", "British English, female"),
    "en_US-lessac-medium": ("en/en_US/lessac/medium/en_US-lessac-medium", "American English, female"),
    "en_US-ryan-medium": ("en/en_US/ryan/medium/en_US-ryan-medium", "American English, male"),
    "en_US-amy-medium": ("en/en_US/amy/medium/en_US-amy-medium", "American English, female"),
}


def voices_dir() -> Path:
    return config.cfg.data_path("voices")


def model_path(voice: str) -> Path:
    """Where a voice's .onnx lives (or would live), without downloading anything."""
    if voice.endswith(".onnx"):
        return Path(os.path.expanduser(voice))
    return voices_dir() / f"{voice}.onnx"


def installed(voice: str) -> bool:
    p = model_path(voice)
    return p.exists() and Path(f"{p}.json").exists()


def _fetch(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310 (fixed https URL)
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, dest)


def ensure(voice: str) -> Path:
    """Return the .onnx path for a voice, downloading it first if it is a catalog name that is not installed yet."""
    p = model_path(voice)
    if installed(voice):
        return p
    if voice.endswith(".onnx"):
        raise FileNotFoundError(f"Piper voice not found: {p} (and its {p.name}.json next to it)")
    if voice not in CATALOG:
        raise FileNotFoundError(f"unknown voice {voice!r}; run `hermes-jarvis voices list`, or set tts.voice to a .onnx path")
    rel = CATALOG[voice][0]
    p.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading voice %s from %s (one time)", voice, BASE)
    for ext in (".onnx.json", ".onnx"):
        _fetch(f"{BASE}/{rel}{ext}", p.parent / f"{voice}{ext}")
    return p
