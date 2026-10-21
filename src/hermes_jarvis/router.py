"""Chooses the brain's profile and session for a spoken request. Optional: it needs a brain that can list its
sessions (Hermes) and an OpenRouter key for the Jev decision model. Without them the rule is simply "continue the
current conversation within the session window, otherwise start a new one in the default profile".

Rule (all numbers are settings):
1. Within `session_window_minutes` of the last voice activity: keep the current profile and session. No model call.
2. Otherwise one Jev call (OpenRouter decisions API) decides two things from the transcript:
   - which earlier conversation it continues, among the last `recent_sessions_count` sessions (titles only), or "new"
   - which profile fits, from the profile descriptions
   A session is resumed only if its probability reaches `session_threshold`. Otherwise a new session starts in the
   chosen profile, or the default profile if the profile probability is below `profile_threshold`.
Any failure falls back to a new session in the default profile, so a routing problem never blocks a reply.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field

import aiohttp

from . import config
from .brains import Brain
from .settings import settings

log = logging.getLogger("hermes_jarvis.router")
JEV_URL: str | None = None  # tests may point this at a fake server; normally the router_url setting is used


@dataclass
class Route:
    profile: str
    session_id: str | None          # None = start a new session
    reason: str                     # window | jev-resume | jev-new | disabled | fallback:<why>
    profile_probs: dict = field(default_factory=dict)
    session_probs: dict = field(default_factory=dict)
    candidates: list = field(default_factory=list)   # [{id, profile, title, age_min}]
    router_ms: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _age(ts: float | None) -> str:
    if not ts:
        return "unknown age"
    mins = max(0, int((time.time() - ts) / 60))
    return f"{mins} min ago" if mins < 90 else f"{mins // 60} h ago" if mins < 2880 else f"{mins // 1440} days ago"


class Router:
    def __init__(self, brain: Brain):
        self.brain = brain
        self._http: aiohttp.ClientSession | None = None

    def available(self) -> bool:
        return (bool(settings.get("router_enabled")) and self.brain.supports_sessions
                and bool(config.secret("OPENROUTER_API_KEY")))

    def _profiles(self) -> list[dict]:
        return [p for p in settings.get("profiles") if p["enabled"]]

    def _default(self) -> str:
        return next(p["name"] for p in settings.get("profiles") if p["is_default"])

    async def _candidates(self, profiles: list[dict]) -> list[dict]:
        sources = list(settings.get("match_sources"))
        n = int(settings.get("recent_sessions_count"))

        async def one(p: dict, source: str) -> list[dict]:
            try:
                sessions = await self.brain.list_sessions(p["name"], limit=n * 3, source=source)
            except Exception as e:
                log.warning("could not list %s sessions for %s: %s", source, p["name"], e)
                return []
            out = []
            for s in sessions:
                if s.get("title") and not s.get("archived") and not s.get("hidden"):
                    out.append({"id": s["id"], "profile": p["name"], "title": s["title"],
                                "last_active": s.get("last_active") or s.get("started_at") or 0})
            return out

        parts = await asyncio.gather(*(one(p, src) for p in profiles for src in sources))
        merged = [c for part in parts for c in part]
        merged.sort(key=lambda c: c["last_active"], reverse=True)
        top = merged[:n]
        for c in top:
            c["age_min"] = max(0, int((time.time() - c["last_active"]) / 60))
        return top

    async def route(self, text: str, cur_session: str | None, cur_profile: str, last_activity: float,
                    ignore_window: bool = False) -> Route:
        window = float(settings.get("session_window_minutes")) * 60
        if cur_session and not ignore_window and time.time() - last_activity <= window:
            return Route(cur_profile, cur_session, "window")
        default = self._default()
        if not self.available():
            return Route(default, None, "disabled")
        t0 = time.monotonic()
        try:
            r = await asyncio.wait_for(self._decide(text, self._profiles(), default, last_activity),
                                       float(settings.get("router_timeout_s")) + 3)
        except Exception as e:
            log.warning("routing failed (%s: %s), using a new %s session", type(e).__name__, e, default)
            return Route(default, None, f"fallback:{type(e).__name__}", router_ms=int((time.monotonic() - t0) * 1000))
        r.router_ms = int((time.monotonic() - t0) * 1000)
        return r

    async def _decide(self, text: str, profiles: list[dict], default: str, last_activity: float) -> Route:
        cands = await self._candidates(profiles)
        questions: dict = {}
        if len(profiles) > 1:
            questions["profile"] = {
                "type": "choice", "instructions": settings.get("router_profile_instructions"),
                "criteria": {p["name"]: p["description"] or p["name"] for p in profiles}}
        if cands:
            crit = {"new": "A new topic. None of the earlier conversations below is about this."}
            for c in cands:
                crit[c["id"]] = f"[{c['profile']}] {c['title']} ({_age(c['last_active'])})"
            questions["session"] = {"type": "choice", "instructions": settings.get("router_session_instructions"),
                                    "criteria": crit}
        if not questions:
            return Route(default, None, "jev-new", candidates=cands)
        body = {"model": settings.get("router_model"),
                "state": {"utterance": text,
                          "minutes_since_last_voice_activity": int((time.time() - last_activity) / 60)
                          if last_activity else None},
                "questions": questions}
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        async with self._http.post(JEV_URL or settings.get("router_url"), json=body,
                                   headers={"Authorization": f"Bearer {config.secret('OPENROUTER_API_KEY')}"},
                                   timeout=aiohttp.ClientTimeout(total=float(settings.get("router_timeout_s")))) as resp:
            if resp.status != 200:
                raise RuntimeError(f"jev HTTP {resp.status}: {(await resp.text())[:150]}")
            answers = (await resp.json()).get("answers", {})

        prof_ans, sess_ans = answers.get("profile"), answers.get("session")
        pprobs = (prof_ans or {}).get("probabilities", {})
        sprobs = (sess_ans or {}).get("probabilities", {})
        by_id = {c["id"]: c for c in cands}

        if sess_ans and sess_ans.get("choice") in by_id and \
                sprobs.get(sess_ans["choice"], 0) >= float(settings.get("session_threshold")):
            c = by_id[sess_ans["choice"]]
            return Route(c["profile"], c["id"], "jev-resume", pprobs, sprobs, cands)
        profile = default
        if prof_ans and prof_ans.get("choice") and \
                pprobs.get(prof_ans["choice"], 0) >= float(settings.get("profile_threshold")):
            profile = prof_ans["choice"]
        return Route(profile, None, "jev-new", pprobs, sprobs, cands)

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()
