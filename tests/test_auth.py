"""Passwords and sessions, without any HTTP."""
import time

import pytest

from hermes_jarvis import auth, config


def test_hashes_verify_only_the_right_password_and_are_salted():
    h1, h2 = auth.hash_password("hunter2hunter2", iterations=1000), auth.hash_password("hunter2hunter2", iterations=1000)
    assert h1 != h2 and h1.startswith("pbkdf2_sha256$1000$")           # a fresh salt every time
    assert auth._verify_hash("hunter2hunter2", h1) and not auth._verify_hash("hunter3hunter3", h1)
    for broken in ("", "x", "md5$1$a$b", "pbkdf2_sha256$x$a$b", "pbkdf2_sha256$1000$!!$!!"):
        assert auth._verify_hash("anything", broken) is False           # malformed values never raise


def test_login_with_a_plain_password(monkeypatch):
    assert not auth.credentials_configured()
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-phrase")
    assert auth.credentials_configured()
    assert auth.check_login("admin", "s3cret-phrase")
    assert not auth.check_login("admin", "s3cret-phrasE")
    assert not auth.check_login("root", "s3cret-phrase")                # the username matters too
    assert not auth.check_login("admin", "")


def test_a_hash_takes_precedence_and_the_plain_value_is_then_ignored(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", auth.hash_password("from-the-hash", iterations=1000))
    monkeypatch.setenv("ADMIN_PASSWORD", "plain-one")
    assert auth.credentials_configured()
    assert auth.check_login("admin", "from-the-hash") and not auth.check_login("admin", "plain-one")


def test_no_credentials_means_nobody_gets_in():
    assert not auth.check_login("admin", "") and not auth.check_login("admin", "admin")


def test_the_configured_username_is_used():
    config.use({"admin": {"user": "tony"}}, base_dir=config.cfg.base_dir)
    import os
    os.environ["ADMIN_PASSWORD"] = "pw-pw-pw-pw"
    try:
        assert auth.check_login("tony", "pw-pw-pw-pw") and not auth.check_login("admin", "pw-pw-pw-pw")
    finally:
        del os.environ["ADMIN_PASSWORD"]


def test_sessions_are_random_and_the_raw_id_is_not_stored():
    m = auth.AuthManager()
    sid1, s1 = m.create("1.2.3.4")
    sid2, s2 = m.create("1.2.3.4")
    assert sid1 != sid2 and s1.csrf != s2.csrf and len(sid1) >= 40
    assert sid1 not in m._sessions and all(sid1 not in k for k in m._sessions)   # only a hash is kept
    assert m.get(sid1) is s1 and m.get("nope") is None and m.get(None) is None and m.get("x" * 500) is None


def test_idle_and_maximum_lifetimes():
    m = auth.AuthManager()
    sid, s = m.create("a")
    s.last_seen -= m.idle_seconds() + 1
    assert m.get(sid) is None and m.count() == 0                         # idle: gone

    sid, s = m.create("a")
    s.created -= m.max_seconds() + 1
    s.last_seen = time.time()
    assert m.get(sid) is None                                            # too old even though it was active


def test_touch_false_does_not_count_as_activity():
    m = auth.AuthManager()
    sid, s = m.create("a")
    s.last_seen -= m.idle_seconds() - 5          # nearly idle
    before = s.last_seen
    assert m.get(sid, touch=False) is s and s.last_seen == before       # a poll must not extend the session
    assert m.get(sid) is s and s.last_seen > before                      # a real request does


def test_destroy_and_the_session_cap():
    m = auth.AuthManager()
    sid, _ = m.create("a")
    m.destroy(sid)
    assert m.get(sid) is None
    first = m.create("a")[0]
    for _ in range(m.MAX_SESSIONS + 5):
        m.create("a")
    assert m.count() <= m.MAX_SESSIONS and m.get(first) is None          # the oldest were evicted


def test_lockout_counts_failures_per_address_and_clears_on_success():
    m = auth.AuthManager()
    for _ in range(m.LOCKOUT_FAILS - 1):
        m.record_failure("1.1.1.1")
    assert not m.locked_out("1.1.1.1")
    m.record_failure("1.1.1.1")
    assert m.locked_out("1.1.1.1") and not m.locked_out("2.2.2.2")
    m.clear_failures("1.1.1.1")
    assert not m.locked_out("1.1.1.1")


def test_csrf_comparison():
    _, s = auth.AuthManager().create("a")
    assert auth.csrf_ok(s, s.csrf)
    for bad in (None, "", "x", s.csrf + "x", s.csrf[:-1]):
        assert not auth.csrf_ok(s, bad)


@pytest.mark.parametrize("minutes,hours", [(1, 1), (45, 24)])
def test_lifetimes_follow_the_config(minutes, hours):
    config.use({"admin": {"session_idle_minutes": minutes, "session_max_hours": hours}}, base_dir=config.cfg.base_dir)
    m = auth.AuthManager()
    assert m.idle_seconds() == minutes * 60 and m.max_seconds() == hours * 3600
