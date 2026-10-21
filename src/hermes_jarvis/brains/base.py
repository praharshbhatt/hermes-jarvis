"""What the rest of the app expects from a brain (the model or agent that writes the answers)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class Brain(Protocol):
    name: str
    supports_profiles: bool   # separate agents reachable by name (Hermes profiles)
    supports_sessions: bool   # server-side conversations that can be listed and resumed

    def turn(self, text: str, session_id: str | None = None, profile: str = "default") -> AsyncIterator[dict]:
        """Stream one turn. Events: {type: session|text|tool|error|done}. `session` comes first and carries the id."""
        ...

    async def list_sessions(self, profile: str = "default", limit: int = 100, source: str | None = None) -> list[dict]:
        ...

    async def check(self) -> list[tuple[str, bool, str]]:
        """Health checks for `hermes-jarvis doctor`: (label, ok, detail)."""
        ...

    async def close(self) -> None:
        ...
