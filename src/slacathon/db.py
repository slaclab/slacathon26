"""Storage for jobs, quota charges, users (API keys + display names), and leaderboard.

Two backends, selected by ``SLACATHON_DB_BACKEND``:

* ``sqlite`` (default): embedded SQLite file at ``settings.db_file`` via stdlib ``sqlite3``.
* ``rqlite``: distributed SQLite over HTTP via ``pyrqlite`` (DB-API 2.0).

pyrqlite constraints that shape this module: ``commit()``/``rollback()`` are no-ops, every
``execute`` is its own request/transaction, no ``executescript``, no ``BEGIN``/``COMMIT`` and
no ``PRAGMA x = y`` statements. All SQL here is therefore single-statement and portable.

Example:
    from slacathon.db import init_db, load_users, get_valid_api_keys
    init_db()
    users = load_users()
"""

import contextlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .settings import settings

logger = logging.getLogger(__name__)

DB_PATH: str = settings.db_file
DB_BACKEND: str = settings.db_backend
_lock = threading.RLock()


def _is_rqlite() -> bool:
    return DB_BACKEND == "rqlite"


def _locked():
    """Serialize callers only for the embedded sqlite backend; Raft serializes rqlite writes."""
    return _lock if not _is_rqlite() else contextlib.nullcontext()


def _db_errors() -> tuple[type[BaseException], ...]:
    """Exception types raised by the active backend."""
    if _is_rqlite():
        from pyrqlite.exceptions import Error as RqliteError
        return (RqliteError,)
    return (sqlite3.Error,)


def _ensure_parent_dir() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def _connect():
    if _is_rqlite():
        from pyrqlite import dbapi2 as rq  # lazy: only needed when the backend is rqlite

        return rq.connect(
            scheme=settings.rqlite_scheme,
            host=settings.rqlite_host,
            port=settings.rqlite_port,
            user=settings.rqlite_user or None,
            password=settings.rqlite_password or None,
            timeout=settings.rqlite_timeout,
        )
    _ensure_parent_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Individual statements (no executescript: pyrqlite sends one statement per request).
_SCHEMA: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS users (
        api_key TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        created_at REAL,
        email TEXT,
        verified INTEGER DEFAULT 0,
        verify_token TEXT,
        expires_at REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        input_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('processing', 'completed')),
        result_json TEXT,
        created_at REAL,
        completed_at REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quota_charges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        charged_at REAL NOT NULL,
        job_id TEXT,
        kind TEXT DEFAULT 'validate',
        charge_token TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leaderboard (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        task_name TEXT NOT NULL DEFAULT '',
        input_json TEXT NOT NULL,
        score REAL NOT NULL,
        solved INTEGER NOT NULL DEFAULT 0,
        timestamp REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_display ON users(display_name)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_quota_user ON quota_charges(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_leaderboard_score ON leaderboard(score)",
]

# Columns added after the first release. Applied only when missing (see _columns()).
# SQLite rejects ``ADD COLUMN ... UNIQUE``; uniqueness lives in _UNIQUE_INDEXES instead.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "email", "ALTER TABLE users ADD COLUMN email TEXT"),
    ("users", "verified", "ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 0"),
    ("users", "verify_token", "ALTER TABLE users ADD COLUMN verify_token TEXT"),
    ("users", "expires_at", "ALTER TABLE users ADD COLUMN expires_at REAL"),
    ("leaderboard", "task_name", "ALTER TABLE leaderboard ADD COLUMN task_name TEXT NOT NULL DEFAULT ''"),
    ("quota_charges", "charge_token", "ALTER TABLE quota_charges ADD COLUMN charge_token TEXT"),
]

# Created after migrations so they also apply to pre-existing databases.
_POST_MIGRATION_INDEXES: list[str] = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_verify_token ON users(verify_token)",
    "CREATE INDEX IF NOT EXISTS idx_leaderboard_task ON leaderboard(task_name)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_quota_token ON quota_charges(charge_token)",
]


def _columns(conn, table: str) -> set[str]:
    """Column names of ``table``. pragma_table_info() is a table-valued function, so it
    works as a plain SELECT on both sqlite3 and rqlite's /db/query."""
    rows = conn.execute(f"SELECT name FROM pragma_table_info('{table}')").fetchall()
    return {r["name"] for r in rows}


def init_db() -> None:
    """Initialize the database: pragmas (sqlite only), tables, column migrations, indexes. Idempotent."""
    with _locked():
        conn = _connect()
        try:
            if not _is_rqlite():
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA busy_timeout = 5000")

            for stmt in _SCHEMA:
                conn.execute(stmt)

            for table, column, alter in _MIGRATIONS:
                if column in _columns(conn, table):
                    continue
                try:
                    conn.execute(alter)
                except _db_errors() as e:
                    # Another process may have added the column between the check and the ALTER.
                    if column not in _columns(conn, table):
                        raise
                    logger.debug(f"Migration {table}.{column} raced with another writer: {e}")

            for stmt in _POST_MIGRATION_INDEXES:
                conn.execute(stmt)

            conn.commit()
            if _is_rqlite():
                logger.info(
                    f"Database initialized (backend=rqlite host={settings.rqlite_host}:{settings.rqlite_port})"
                )
            else:
                logger.info(f"Database initialized (backend=sqlite path={DB_PATH})")
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
    """Return {api_key: display_name} for verified users."""
    with _locked():
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT api_key, display_name FROM users WHERE verified = 1"
            ).fetchall()
            return {r["api_key"]: r["display_name"] for r in rows}
        finally:
            conn.close()


def get_valid_api_keys() -> set[str]:
    """Return verified API keys only."""
    with _locked():
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT api_key FROM users WHERE verified = 1"
            ).fetchall()
            return {r["api_key"] for r in rows}
        finally:
            conn.close()


def upsert_user(api_key: str, display_name: str) -> None:
    """Insert or update a user (for admin tools or migration). Skips verified users."""
    with _locked():
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO users (api_key, display_name, created_at, verified) VALUES (?, ?, ?, 1)
                ON CONFLICT(api_key) DO UPDATE SET display_name=excluded.display_name
                WHERE verified = 0 OR verified IS NULL
                """,
                (api_key, display_name, time.time())
            )
            conn.commit()
        finally:
            conn.close()


# -----------------------
# Registration helpers
# -----------------------

def create_unverified_user(
    email: str,
    display_name: str,
    verify_token: str,
    expires_at: float,
) -> str:
    """Create a new unverified user row. Returns the row id (display_name used as placeholder api_key)."""
    import secrets as _secrets
    row_id = _secrets.token_urlsafe(16)
    with _locked():
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO users (api_key, display_name, created_at, email, verified, verify_token, expires_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (row_id, display_name.strip()[:40], time.time(), email.lower(), verify_token, expires_at),
            )
            conn.commit()
            return row_id
        finally:
            conn.close()


def get_user_by_email(email: str) -> dict | None:
    with _locked():
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower(),)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_user_by_token(token: str) -> dict | None:
    with _locked():
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE verify_token = ?", (token,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def mark_user_verified(row_id: str, api_key: str) -> None:
    with _locked():
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE users
                SET api_key = ?, verified = 1, expires_at = NULL, verify_token = NULL
                WHERE api_key = ?
                """,
                (api_key, row_id),
            )
            conn.commit()
        finally:
            conn.close()


def delete_user_by_id(row_id: str) -> None:
    with _locked():
        conn = _connect()
        try:
            conn.execute("DELETE FROM users WHERE api_key = ?", (row_id,))
            conn.commit()
        finally:
            conn.close()


def delete_expired_unverified_users() -> int:
    """Delete unverified users whose token has expired. Returns count deleted."""
    import time as _time
    now = _time.time()
    with _locked():
        conn = _connect()
        try:
            cur = conn.execute(
                "DELETE FROM users WHERE verified = 0 AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


# -----------------------
# Jobs
# -----------------------

def load_jobs() -> dict[str, dict]:
    """Load all jobs into a dict keyed by job_id."""
    with _locked():
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
    with _locked():
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
    with _locked():
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
    with _locked():
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
    The check + insert is a single conditional INSERT statement, so it is atomic on
    both backends (sqlite serializes via _lock, rqlite via the Raft log). No explicit
    transaction is used because pyrqlite cannot express BEGIN/COMMIT. Each charge row
    carries a unique charge_token so the caller can tell whether its INSERT took effect.

    Returns the new charge count on success.
    Raises RuntimeError if the user is already at or over the limit.
    """
    # rqlite does not report rows_affected for INSERT and last_insert_id is stale when the
    # conditional INSERT matches no row, so success is detected by looking up a unique token.
    token = uuid.uuid4().hex
    with _locked():
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO quota_charges (user_id, charged_at, job_id, kind, charge_token)
                SELECT ?, ?, ?, ?, ?
                WHERE (SELECT COUNT(*) FROM quota_charges WHERE user_id = ?) < ?
                """,
                (user_id, charged_at, job_id, kind, token, user_id, limit),
            )
            conn.commit()
            inserted = conn.execute(
                "SELECT 1 FROM quota_charges WHERE charge_token = ?", (token,)
            ).fetchone()
            if inserted is None:
                raise RuntimeError(
                    f"Validation limit of {limit} reached for this API key"
                )
            row = conn.execute(
                "SELECT COUNT(*) as c FROM quota_charges WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["c"]) if row else 1
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed atomic quota charge for user {user_id}: {e}")
            raise
        finally:
            conn.close()


# -----------------------
# Leaderboard
# -----------------------

def get_all_leaderboard_entries(task_name: str) -> list[dict]:
    """Return leaderboard rows for the given task, ordered by score ascending (caller re-sorts as needed)."""
    with _locked():
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, user_id, input_json, score, solved, timestamp FROM leaderboard "
                "WHERE task_name = ? ORDER BY score ASC",
                (task_name,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "input": _json_loads(r["input_json"]),
                    "score": r["score"],
                    "solved": bool(r["solved"]),
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        finally:
            conn.close()


def insert_leaderboard_entry(user_id: str, task_name: str, input: dict, score: float, solved: bool, timestamp: float) -> int:
    """Insert a leaderboard row. Returns the new row id."""
    with _locked():
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT INTO leaderboard (user_id, task_name, input_json, score, solved, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, task_name, _json_dumps(input), score, int(solved), timestamp),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def input_exists_in_leaderboard(task_name: str, input: dict) -> bool:
    """Return True if an entry with exactly this input already exists for the given task."""
    input_str = _json_dumps(input)
    with _locked():
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM leaderboard WHERE task_name = ? AND input_json = ? LIMIT 1",
                (task_name, input_str),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def trim_leaderboard(task_name: str, max_size: int, minimize: bool) -> None:
    """Keep only the top `max_size` entries for the given task; remove the rest."""
    order = "ASC" if minimize else "DESC"
    with _locked():
        conn = _connect()
        try:
            conn.execute(
                f"""
                DELETE FROM leaderboard WHERE task_name = ? AND id NOT IN (
                    SELECT id FROM leaderboard WHERE task_name = ? ORDER BY score {order} LIMIT ?
                )
                """,
                (task_name, task_name, max_size),
            )
            conn.commit()
        finally:
            conn.close()


def get_job(job_id: str) -> dict | None:
    """Fetch a single job by ID directly from DB."""
    with _locked():
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
