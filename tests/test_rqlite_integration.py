"""Live rqlite integration tests.

Skipped unless ``SLACATHON_RQLITE_HOST`` is set. Run locally with:

    docker compose --profile rqlite up -d rqlite
    SLACATHON_RQLITE_HOST=localhost pytest -m rqlite

or against a native binary: ``rqlited -node-id 1 /tmp/rqlite-node``.

Every test uses a unique prefix so the suite can run repeatedly against the same node.
"""

import os
import threading
import time
import uuid

import pytest

pytestmark = pytest.mark.rqlite

RQLITE_HOST = os.environ.get("SLACATHON_RQLITE_HOST")

if not RQLITE_HOST:
    pytest.skip("SLACATHON_RQLITE_HOST not set", allow_module_level=True)


@pytest.fixture(scope="module")
def rq_db():
    """db module pointed at the live rqlite node for the duration of this module."""
    from slacathon import db
    from slacathon.settings import settings

    saved = (db.DB_BACKEND, settings.rqlite_host, settings.rqlite_port, settings.rqlite_user, settings.rqlite_password)
    db.DB_BACKEND = "rqlite"
    object.__setattr__(settings, "rqlite_host", RQLITE_HOST)
    object.__setattr__(settings, "rqlite_port", int(os.environ.get("SLACATHON_RQLITE_PORT", "4001")))
    object.__setattr__(settings, "rqlite_user", os.environ.get("SLACATHON_RQLITE_USER", ""))
    object.__setattr__(settings, "rqlite_password", os.environ.get("SLACATHON_RQLITE_PASSWORD", ""))
    db.init_db()
    yield db
    db.DB_BACKEND = saved[0]
    for key, val in zip(("rqlite_host", "rqlite_port", "rqlite_user", "rqlite_password"), saved[1:]):
        object.__setattr__(settings, key, val)


@pytest.fixture
def uid():
    return uuid.uuid4().hex[:8]


def test_init_db_twice_and_columns(rq_db):
    rq_db.init_db()
    conn = rq_db._connect()
    try:
        assert {"api_key", "display_name", "email", "verified", "verify_token", "expires_at"} <= rq_db._columns(conn, "users")
        assert "task_name" in rq_db._columns(conn, "leaderboard")
    finally:
        conn.close()


def test_registration_flow(rq_db, uid):
    email = f"{uid}@example.com"
    row_id = rq_db.create_unverified_user(email, "Int Test", f"tok-{uid}", time.time() + 3600)
    row = rq_db.get_user_by_email(email)
    assert row is not None and row["verified"] == 0 and row["api_key"] == row_id
    assert rq_db.get_user_by_token(f"tok-{uid}")["email"] == email
    assert row_id not in rq_db.get_valid_api_keys()

    rq_db.mark_user_verified(row_id, f"key-{uid}")
    assert f"key-{uid}" in rq_db.get_valid_api_keys()
    assert rq_db.load_users()[f"key-{uid}"] == "Int Test"
    assert rq_db.get_user_by_token(f"tok-{uid}") is None

    rq_db.delete_user_by_id(f"key-{uid}")
    assert rq_db.get_user_by_email(email) is None


def test_upsert_user_skips_verified(rq_db, uid):
    key = f"up-{uid}"
    rq_db.upsert_user(key, "First")
    rq_db.upsert_user(key, "Second")  # verified=1 after first upsert -> name must not change
    assert rq_db.load_users()[key] == "First"
    rq_db.delete_user_by_id(key)


def test_expired_unverified_cleanup(rq_db, uid):
    rq_db.create_unverified_user(f"exp-{uid}@example.com", "Exp", f"exptok-{uid}", time.time() - 10)
    assert rq_db.delete_expired_unverified_users() >= 1
    assert rq_db.get_user_by_email(f"exp-{uid}@example.com") is None


def test_jobs_roundtrip(rq_db, uid):
    job_id = f"job-{uid}"
    rq_db.insert_job({"job_id": job_id, "user_id": f"u-{uid}", "input": {"x": [1, 2]}, "created_at": time.time()})
    assert rq_db.get_job(job_id)["status"] == "processing"
    rq_db.update_job(job_id, status="completed", result={"score": 1.5}, completed_at=time.time())
    job = rq_db.get_job(job_id)
    assert job["status"] == "completed" and job["result"] == {"score": 1.5}
    assert job_id in rq_db.load_jobs()


def test_charge_quota_sequential(rq_db, uid):
    user = f"q-{uid}"
    assert rq_db.charge_quota(user, 2, time.time()) == 1
    assert rq_db.charge_quota(user, 2, time.time()) == 2
    with pytest.raises(RuntimeError):
        rq_db.charge_quota(user, 2, time.time())
    assert rq_db.get_user_charge_count(user) == 2


def test_charge_quota_concurrent(rq_db, uid):
    user = f"qc-{uid}"
    limit, n = 5, 20
    ok, bad = [], []
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        try:
            ok.append(rq_db.charge_quota(user, limit, time.time()))
        except RuntimeError as e:
            bad.append(e)

    ts = [threading.Thread(target=worker) for _ in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(ok) == limit and len(bad) == n - limit
    assert rq_db.get_user_charge_count(user) == limit


def test_leaderboard_insert_dedup_trim(rq_db, uid):
    task = f"task-{uid}"
    ids = [
        rq_db.insert_leaderboard_entry(f"u{i}", task, {"v": i}, float(i), i == 0, time.time())
        for i in range(6)
    ]
    assert all(isinstance(i, int) and i > 0 for i in ids)
    assert rq_db.input_exists_in_leaderboard(task, {"v": 3})
    assert not rq_db.input_exists_in_leaderboard(task, {"v": 99})

    rq_db.trim_leaderboard(task, max_size=3, minimize=True)
    entries = rq_db.get_all_leaderboard_entries(task)
    assert [e["score"] for e in entries] == [0.0, 1.0, 2.0]
    assert entries[0]["solved"] is True
