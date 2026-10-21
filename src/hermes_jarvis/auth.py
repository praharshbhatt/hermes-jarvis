"""Login and sessions for the admin UI.

- The credential is ADMIN_PASSWORD (plain, from the environment) or ADMIN_PASSWORD_HASH (a PBKDF2 hash made by
  `hermes-jarvis hash-password`, so the secret itself need not sit in `.env`). Comparisons are constant-time.
- A successful login creates a server-side session with a random id. The browser only holds that id, in an HttpOnly,
  SameSite=Strict cookie (and Secure when the request came in over https). Sessions expire after being idle and after a
  maximum age, and every login gets a new id.
- State-changing requests need the session's CSRF token in `X-CSRF-Token`, and a cross-origin `Origin` is refused.
- Failed logins are slowed down, and an address is locked out after repeated failures.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field

from . import config

COOKIE = "hj_session"
COOKIE_SECURE = "__Host-hj_session"  # the __Host- prefix makes a Secure cookie impossible to override from another subdomain
PBKDF2_ITERATIONS = 600_000


# ----- password handling -----
def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _verify_hash(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def credentials_configured() -> bool:
    return bool(config.secret("ADMIN_PASSWORD_HASH") or config.secret("ADMIN_PASSWORD"))


def check_login(username: str, password: str) -> bool:
    """Constant-time check of both fields. Always does the same work whichever one is wrong."""
    user_ok = hmac.compare_digest(hashlib.sha256(username.encode()).digest(),
                                  hashlib.sha256(config.cfg.admin.user.encode()).digest())
    stored_hash = config.secret("ADMIN_PASSWORD_HASH")
    if stored_hash:
        pw_ok = _verify_hash(password, stored_hash)
    else:
        plain = config.secret("ADMIN_PASSWORD")
        pw_ok = bool(plain) and hmac.compare_digest(hashlib.sha256(password.encode()).digest(),
                                                    hashlib.sha256(plain.encode()).digest())
    return user_ok and pw_ok


# ----- sessions -----
@dataclass
class Session:
    csrf: str
    created: float
    last_seen: float
    remote: str
    streams: int = 0
    key: str = field(default="", repr=False)


class AuthManager:
    LOCKOUT_FAILS, LOCKOUT_WINDOW = 10, 300.0
    MAX_SESSIONS = 20

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}  # sha256(session id) -> session: the raw id is never stored
        self._failures: dict[str, list[float]] = {}

    # lifetimes come from the config each time, so tests and restarts agree
    @staticmethod
    def idle_seconds() -> float:
        return float(config.cfg.admin.session_idle_minutes) * 60

    @staticmethod
    def max_seconds() -> float:
        return float(config.cfg.admin.session_max_hours) * 3600

    @staticmethod
    def _key(sid: str) -> str:
        return hashlib.sha256(sid.encode()).hexdigest()

    def create(self, remote: str) -> tuple[str, Session]:
        self._purge()
        while len(self._sessions) >= self.MAX_SESSIONS:
            self._sessions.pop(min(self._sessions, key=lambda k: self._sessions[k].last_seen))
        sid = secrets.token_urlsafe(32)
        now = time.time()
        s = Session(csrf=secrets.token_urlsafe(32), created=now, last_seen=now, remote=remote, key=self._key(sid))
        self._sessions[s.key] = s
        return sid, s

    def get(self, sid: str | None, touch: bool = True) -> Session | None:
        """The session for a cookie value, or None if unknown or expired. `touch=False` checks without counting the
        request as activity (background polling and the live stream must not keep a session alive forever)."""
        if not sid or len(sid) > 200:
            return None
        s = self._sessions.get(self._key(sid))
        if s is None:
            return None
        now = time.time()
        if now - s.last_seen > self.idle_seconds() or now - s.created > self.max_seconds():
            self._sessions.pop(s.key, None)
            return None
        if touch:
            s.last_seen = now
        return s

    def destroy(self, sid: str | None) -> None:
        if sid:
            self._sessions.pop(self._key(sid), None)

    def _purge(self) -> None:
        now = time.time()
        for k, s in list(self._sessions.items()):
            if now - s.last_seen > self.idle_seconds() or now - s.created > self.max_seconds():
                del self._sessions[k]

    def count(self) -> int:
        self._purge()
        return len(self._sessions)

    # ----- lockout -----
    def locked_out(self, who: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(who, []) if now - t < self.LOCKOUT_WINDOW]
        self._failures[who] = recent
        return len(recent) >= self.LOCKOUT_FAILS

    def record_failure(self, who: str) -> None:
        self._failures.setdefault(who, []).append(time.time())

    def clear_failures(self, who: str) -> None:
        self._failures.pop(who, None)


def csrf_ok(session: Session, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(token.encode(), session.csrf.encode())
