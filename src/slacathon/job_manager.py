import time
import threading
import uuid
import logging
import math
import numpy as np

from .settings import settings
from .db import (
    init_db,
    load_jobs as db_load_jobs,
    insert_job,
    update_job,
    charge_quota,
    get_user_charge_count,
    get_job as db_get_job,
)

logger = logging.getLogger(__name__)

MAX_VALIDATIONS_PER_USER = settings.max_validations_per_user

jobs: dict = {}
jobs_lock = threading.RLock()


def load_jobs():
    """Load jobs from the database into the in-memory cache. Returns the jobs dict."""
    global jobs
    init_db()
    try:
        jobs = db_load_jobs()
        logger.info(f"Loaded {len(jobs)} jobs from database")
    except Exception as e:
        logger.error(f"Failed to load jobs from database: {e}")
        jobs = {}
    return jobs


def get_job(job_id: str) -> dict | None:
    with jobs_lock:
        if job_id in jobs:
            return jobs[job_id]
    # Fallback to database (single lookup)
    rec = db_get_job(job_id)
    if rec:
        with jobs_lock:
            jobs[job_id] = rec
        return rec
    return None


def create_job(user_id: str, input_data: dict) -> str:
    """Build job record, charge quota (durable), persist to DB and memory."""
    job_id = str(uuid.uuid4())
    job_record = {
        "job_id": job_id,
        "user_id": user_id,
        "input": input_data,
        "status": "processing",
        "result": None,
        "created_at": time.time(),
        "completed_at": None
    }
    charge_validation_quota(user_id, record=job_record)
    insert_job(job_record)  # persist job row to DB
    with jobs_lock:
        jobs[job_id] = job_record
    logger.info(f"Created job {job_id} for user {user_id}")
    return job_id


def charge_validation_quota(user_id: str, *, record: dict) -> None:
    """Atomic quota enforcement.

    Delegates to the DB layer for an atomic check + insert (using BEGIN IMMEDIATE)
    to avoid TOCTOU races. Updates the in-memory count from the authoritative DB result.
    Used by both /validate and /submit paths.
    """
    job_id = record.get("job_id")
    kind = record.get("kind", "validate" if job_id else "submit")
    charged_at = record.get("created_at", time.time())

    # This call is fully atomic in the database
    charge_quota(
        user_id, MAX_VALIDATIONS_PER_USER, charged_at, job_id, kind
    )


def make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer, np.floating)):
        val = float(obj)
        if not math.isfinite(val):
            return settings.failure_score
        return val
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return settings.failure_score
        return obj
    return obj


def complete_job(job_id: str, result: dict):
    safe_result = make_json_safe(result)
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = safe_result
            jobs[job_id]["completed_at"] = time.time()
    # Persist update to DB (single row per job)
    update_job(
        job_id,
        status="completed",
        result=safe_result,
        completed_at=time.time(),
    )
    logger.info(f"Job {job_id} completed with score {safe_result.get('score')}")





def set_max_validations_per_user(limit: int):
    """Set the effective per-user validation limit (called by main after loading active task)."""
    global MAX_VALIDATIONS_PER_USER
    MAX_VALIDATIONS_PER_USER = limit
    logger.info(f"Validation limit set to {limit} (from active task or settings)")


def get_quota_info(user_id: str) -> dict:
    """Return quota status for API responses.

    Uses live count from the database as the source of truth (prevents drift).
    The in-memory cache is still maintained for other internal use.
    """
    limit = MAX_VALIDATIONS_PER_USER
    used = get_user_charge_count(user_id)
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used)
    }


# Initialize DB and populate in-memory job cache from it.
init_db()
load_jobs()
