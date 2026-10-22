"""Backend-portable db behaviour (runs on the embedded sqlite backend).

Coverage:
  - init_db() is idempotent and migrations report every expected column
  - UNIQUE constraints on users.email / users.verify_token are enforced via indexes
  - charge_quota: increments below the limit, raises at the limit (single-statement path)
  - charge_quota under concurrent callers never exceeds the limit
"""

import sqlite3
import threading
import time

import pytest

from slacathon import db


@pytest.fixture(autouse=True)
def _use_app_db(app):
    """Ensure the shared test DB is initialized before each test."""
    yield


def test_init_db_idempotent():
    db.init_db()
    db.init_db()
    conn = db._connect()
    try:
        cols = db._columns(conn, "users")
    finally:
        conn.close()
    assert {"api_key", "display_name", "created_at", "email", "verified", "verify_token", "expires_at"} <= cols


def test_migrations_apply_to_legacy_schema(tmp_path, monkeypatch):
    """A DB created before the email/verify columns existed gains them on init_db()."""
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE users (api_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at REAL);
        CREATE TABLE leaderboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, input_json TEXT NOT NULL,
            score REAL NOT NULL, solved INTEGER NOT NULL DEFAULT 0, timestamp REAL NOT NULL
        );
        INSERT INTO users (api_key, display_name) VALUES ('k1', 'Legacy');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_PATH", str(legacy))
    db.init_db()
    db.init_db()

    conn = db._connect()
    try:
        assert {"email", "verified", "verify_token", "expires_at"} <= db._columns(conn, "users")
        assert "task_name" in db._columns(conn, "leaderboard")
        assert conn.execute("SELECT display_name FROM users WHERE api_key='k1'").fetchone()[0] == "Legacy"
    finally:
        conn.close()


def test_email_unique_enforced():
    now = time.time()
    db.create_unverified_user("unique@example.com", "A", "tok-unique-1", now + 100)
    with pytest.raises(db._db_errors()):
        db.create_unverified_user("unique@example.com", "B", "tok-unique-2", now + 100)


def test_charge_quota_increments_then_blocks():
    user = "quota-user-portable"
    assert db.charge_quota(user, limit=2, charged_at=time.time()) == 1
    assert db.charge_quota(user, limit=2, charged_at=time.time()) == 2
    with pytest.raises(RuntimeError):
        db.charge_quota(user, limit=2, charged_at=time.time())
    assert db.get_user_charge_count(user) == 2


def test_charge_quota_concurrent_never_exceeds_limit():
    user = "quota-user-concurrent"
    limit = 5
    successes: list[int] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(20)

    def worker():
        barrier.wait()
        try:
            successes.append(db.charge_quota(user, limit=limit, charged_at=time.time()))
        except RuntimeError as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == limit
    assert len(errors) == 20 - limit
    assert db.get_user_charge_count(user) == limit
