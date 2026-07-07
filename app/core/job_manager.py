import json
import time
import uuid
import logging
import math
import numpy as np

from sqlmodel import Session, select

from app.settings import settings
from app.models.job import Job

logger = logging.getLogger(__name__)

MAX_VALIDATIONS_PER_USER = settings.max_validations_per_user


def set_max_validations_per_user(limit: int):
    global MAX_VALIDATIONS_PER_USER
    MAX_VALIDATIONS_PER_USER = limit
    logger.info(f"Validation limit set to {limit} (from active task or settings)")


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


def _job_to_dict(job: Job) -> dict:
    return {
        "job_id": job.id,
        "user_id": job.user_id,
        "input": json.loads(job.input_json),
        "status": job.status,
        "result": json.loads(job.result_json) if job.result_json else None,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }


def get_quota_info(user_id: str, session: Session) -> dict:
    limit = MAX_VALIDATIONS_PER_USER
    used = session.exec(select(Job).where(Job.user_id == user_id)).all()
    used_count = len(used)
    return {
        "used": used_count,
        "limit": limit,
        "remaining": max(0, limit - used_count),
    }


def charge_validation_quota(user_id: str, session: Session) -> None:
    used = len(session.exec(select(Job).where(Job.user_id == user_id)).all())
    if used >= MAX_VALIDATIONS_PER_USER:
        raise RuntimeError(
            f"Validation limit of {MAX_VALIDATIONS_PER_USER} reached for this API key"
        )


def create_job(user_id: str, input_data: dict, session: Session) -> str:
    charge_validation_quota(user_id, session)
    job = Job(
        id=str(uuid.uuid4()),
        user_id=user_id,
        input_json=json.dumps(input_data),
        status="processing",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    logger.info(f"Created job {job.id} for user {user_id}")
    return job.id


def get_job(job_id: str, session: Session) -> dict | None:
    job = session.get(Job, job_id)
    if not job:
        return None
    return _job_to_dict(job)


def complete_job(job_id: str, result: dict, session: Session):
    safe_result = make_json_safe(result)
    job = session.get(Job, job_id)
    if job:
        job.status = "completed"
        job.result_json = json.dumps(safe_result)
        job.completed_at = time.time()
        session.add(job)
        session.commit()
        logger.info(f"Job {job_id} completed with score {safe_result.get('score')}")
