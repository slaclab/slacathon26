"""SQLite-backed storage for jobs, quota charges, and users (API keys + display names).

This module is the foundation for the scoped migration. Leaderboard remains in JSON.

Example:
    from slacathon.db import init_db, load_users, get_valid_api_keys
    init_db()
    users = load_users()
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .settings import settings

logger = logging.getLogger(__name__)

DB_PATH: str = settings.db_file
_lock = threading.RLock()


def _ensure_parent_dir() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_parent_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database: pragmas + tables. Idempotent. Seeds minimal users if empty."""
    with _lock:
        conn = _connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    api_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at REAL DEFAULT (strftime('%s','now'))
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('processing', 'completed')),
                    result_json TEXT,
                    created_at REAL,
                    completed_at REAL
                );

                CREATE TABLE IF NOT EXISTS quota_charges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    charged_at REAL NOT NULL,
                    job_id TEXT,
                    kind TEXT DEFAULT 'validate'
                );

                CREATE INDEX IF NOT EXISTS idx_users_display ON users(display_name);
                CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
                CREATE INDEX IF NOT EXISTS idx_quota_user ON quota_charges(user_id);
            """)

            conn.commit()
            logger.info(f"Database initialized at {DB_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
        finally:
            conn.close()


def _json_dumps(obj: Any) -> str:
    if obj is None:
        return "null"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _json_loads(s: str | None) -> Any:
    if not s or s == "null":
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


# -----------------------
# Users / API Keys
# -----------------------

def load_users() -> dict[str, str]:
    """Return {api_key: display_name}."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT api_key, display_name FROM users").fetchall()
            return {r["api_key"]: r["display_name"] for r in rows}
        finally:
            conn.close()


def get_valid_api_keys() -> set[str]:
    """Return the set of valid API keys from the users table."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT api_key FROM users").fetchall()
            return {r["api_key"] for r in rows}
        finally:
            conn.close()


def upsert_user(api_key: str, display_name: str) -> None:
    """Insert or update a user (for future admin tools or migration)."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO users (api_key, display_name) VALUES (?, ?)",
                (api_key, display_name)
            )
            conn.commit()
        finally:
            conn.close()


# -----------------------
# Jobs
# -----------------------

def load_jobs() -> dict[str, dict]:
    """Load all jobs into a dict keyed by job_id."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT job_id, user_id, input_json, status, result_json, created_at, completed_at FROM jobs"
            ).fetchall()
            jobs: dict[str, dict] = {}
            for r in rows:
                jobs[r["job_id"]] = {
                    "job_id": r["job_id"],
                    "user_id": r["user_id"],
                    "input": _json_loads(r["input_json"]),
                    "status": r["status"],
                    "result": _json_loads(r["result_json"]),
                    "created_at": r["created_at"],
                    "completed_at": r["completed_at"],
                }
            return jobs
        finally:
            conn.close()


def insert_job(job: dict) -> None:
    """Insert a job record (expects keys: job_id, user_id, input, status, ...)."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs
                (job_id, user_id, input_json, status, result_json, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["job_id"],
                    job["user_id"],
                    _json_dumps(job.get("input")),
                    job.get("status", "processing"),
                    _json_dumps(job.get("result")),
                    job.get("created_at"),
                    job.get("completed_at"),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def update_job(job_id: str, **fields) -> None:
    """Partial update for a job (e.g. status, result, completed_at)."""
    if not fields:
        return
    allowed = {"status", "result", "completed_at", "result_json"}
    set_parts = []
    values = []
    for k, v in fields.items():
        if k in allowed:
            if k == "result":
                set_parts.append("result_json = ?")
                values.append(_json_dumps(v))
            else:
                set_parts.append(f"{k} = ?")
                values.append(v)
    if not set_parts:
        return
    values.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(set_parts)} WHERE job_id = ?"
    with _lock:
        conn = _connect()
        try:
            conn.execute(sql, values)
            conn.commit()
        finally:
            conn.close()


# -----------------------
# Quota charges
# -----------------------

def get_user_charge_count(user_id: str) -> int:
    """Return how many charges this user has (source of truth for quota after restart)."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM quota_charges WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()


def charge_quota(
    user_id: str,
    limit: int,
    charged_at: float,
    job_id: str | None = None,
    kind: str = "validate",
) -> int:
    """Atomically check quota limit and insert a charge record if under the limit.

    This is the atomic primitive that prevents TOCTOU races on quota enforcement.
    The check + insert happens inside a single SQLite transaction with BEGIN IMMEDIATE.

    Returns the new charge count on success.
    Raises RuntimeError if the user is already at or over the limit.
    """
    with _lock:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT COUNT(*) as c FROM quota_charges WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            current = int(row["c"]) if row else 0

            if current >= limit:
                conn.execute("ROLLBACK")
                raise RuntimeError(
                    f"Validation limit of {limit} reached for this API key"
                )

            conn.execute(
                "INSERT INTO quota_charges (user_id, charged_at, job_id, kind) VALUES (?, ?, ?, ?)",
                (user_id, charged_at, job_id, kind),
            )
            conn.execute("COMMIT")
            return current + 1

        except RuntimeError:
            # Re-raise the quota limit error cleanly
            raise
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"Failed atomic quota charge for user {user_id}: {e}")
            raise
        finally:
            conn.close()





def get_job(job_id: str) -> dict | None:
    """Fetch a single job by ID directly from DB."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT job_id, user_id, input_json, status, result_json, created_at, completed_at "
                "FROM jobs WHERE job_id = ?",
                (job_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "job_id": row["job_id"],
                "user_id": row["user_id"],
                "input": _json_loads(row["input_json"]),
                "status": row["status"],
                "result": _json_loads(row["result_json"]),
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
            }
        finally:
            conn.close()





