import json
import os
import time
import threading
import uuid
import logging
import math
import numpy as np

from settings import settings

logger = logging.getLogger(__name__)

JOBS_FILE = settings.jobs_file

MAX_VALIDATIONS_PER_USER = settings.max_validations_per_user

jobs: dict = {}
jobs_lock = threading.RLock()
append_lock = threading.Lock()

# Live per-user validation counts (populated after rebuilder definition below).
# Quota ownership consolidated in job_manager.
user_validation_counts: dict = {}


def load_jobs():
    global jobs
    jobs = {}
    if not os.path.exists(JOBS_FILE):
        logger.info("No existing jobs file found, starting fresh")
        return
    try:
        with open(JOBS_FILE, 'r') as f:
            lines = f.readlines()
        recent_lines = lines[-300:]
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
                if isinstance(job, dict) and "job_id" in job:
                    job["input"] = job.get("input") or {}
                    if not isinstance(job.get("input"), dict):
                        job["input"] = {}
                    jobs[job["job_id"]] = job
            except Exception:
                continue
        logger.info(f"Loaded {len(jobs)} recent jobs into memory (full history kept in the file)")

    except Exception as e:
        logger.error(f"Failed to load jobs: {e}")
        jobs = {}


def _append_job_record(job_record: dict) -> bool:
    try:
        with append_lock:
            with open(JOBS_FILE, "a") as f:
                f.write(json.dumps(job_record) + "\n")
        return True
    except Exception as e:
        logger.error(f"Failed to append job record: {e}")
        return False


def get_job(job_id: str) -> dict | None:
    with jobs_lock:
        if job_id in jobs:
            return jobs[job_id]
    try:
        with open(JOBS_FILE, 'r') as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("job_id") == job_id:
                    rec["input"] = rec.get("input") or {}
                    if not isinstance(rec.get("input"), dict):
                        rec["input"] = {}
                    with jobs_lock:
                        jobs[job_id] = rec
                    return rec
            except Exception:
                continue
    except Exception:
        pass
    return None


def create_job(user_id: str, input_data: dict) -> str:
    """Thin wrapper: build job record then delegate to charge (single owner for check+persist+count)."""
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
    with jobs_lock:
        jobs[job_id] = job_record
    charge_validation_quota(user_id, record=job_record)
    logger.info(f"Created job {job_id} for user {user_id}")
    return job_id


def charge_validation_quota(user_id: str, *, record: dict) -> None:
    """Single durable primitive: check limit (raise 429), append record, inc count ONLY on successful append.
    Used by both /validate (full job record) and /submit (minimal record) so both paths persist and are counted on restart.
    """
    current = user_validation_counts.get(user_id, 0)
    if current >= MAX_VALIDATIONS_PER_USER:
        raise RuntimeError(
            f"Validation limit of {MAX_VALIDATIONS_PER_USER} reached for this API key"
        )
    if _append_job_record(record):
        user_validation_counts[user_id] = current + 1


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
    job_record = None
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = safe_result
            jobs[job_id]["completed_at"] = time.time()
            job_record = dict(jobs[job_id])
    if job_record:
        _append_job_record(job_record)
        logger.info(f"Job {job_id} completed with score {safe_result.get('score')}")


load_jobs()

def get_user_validation_counts() -> dict:
    """Rebuild user validation counts from full jobs history for accurate quota at startup."""
    counts = {}
    if not os.path.exists(JOBS_FILE):
        return counts
    try:
        with open(JOBS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    job = json.loads(line)
                    uid = job.get("user_id")
                    if uid:
                        counts[uid] = counts.get(uid, 0) + 1
                except Exception:
                    continue
    except Exception:
        pass
    return counts


def set_max_validations_per_user(limit: int):
    """Set the effective per-user validation limit (called by main after loading active task)."""
    global MAX_VALIDATIONS_PER_USER
    MAX_VALIDATIONS_PER_USER = limit
    logger.info(f"Validation limit set to {limit} (from active task or settings)")


def get_quota_info(user_id: str) -> dict:
    """Return quota status for API responses. Single source of truth (eliminates duplication in main.py)."""
    limit = MAX_VALIDATIONS_PER_USER
    used = user_validation_counts.get(user_id, 0)
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used)
    }


# Populate live counts from job history now that the rebuilder function is defined.
# This replaces the previous assignment that lived in middleware.py.
user_validation_counts = get_user_validation_counts()
