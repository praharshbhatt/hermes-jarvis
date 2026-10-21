"""Brains: the model or agent that writes the answers. Pick one with `brain.type` in config.yaml."""
from __future__ import annotations

from .. import config
from .base import Brain


def make_brain() -> Brain:
    kind = config.cfg.brain.type
    if kind == "hermes":
        from .hermes import HermesBrain
        return HermesBrain()
    if kind == "openai":
        from .openai_compat import OpenAIBrain
        return OpenAIBrain()
    raise ValueError(f"unknown brain.type {kind!r} (use 'hermes' or 'openai')")


__all__ = ["Brain", "make_brain"]
