import json
import logging

from fastapi import APIRouter, Depends
from sqlmodel import Session as DBSession, select

from app.core.middleware import get_leaderboard, get_display_name, verify_api_key
from app.core.task_loader import load_active_task
from app.db import get_session
from app.models.job import Job
from app.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/leaderboard")
async def view_leaderboard(session: DBSession = Depends(get_session)):
    logger.info("Leaderboard API request received")
    board = get_leaderboard(session)
    return {
        "total_entries": len(board),
        "leaderboard": board
    }


@router.get("/task")
async def get_task_info():
    TASK = load_active_task()
    return {
        "name": getattr(TASK, "TASK_NAME", "Unknown Task"),
        "input_schema": TASK.Input.model_json_schema(),
        "result_schema": TASK.Result.model_json_schema(),
        "parameter_labels": getattr(TASK, "INPUT_LABELS", None),
        "bounds": getattr(TASK, "BOUNDS", None),
        "target": getattr(TASK, "TARGET", None),
        "minimize": getattr(TASK, "MINIMIZE", None),
        "failure_score": getattr(TASK, "FAILURE_SCORE", None),
        "max_validations_per_user": getattr(TASK, "MAX_VALIDATIONS_PER_USER", None),
    }


@router.get("/history")
async def get_history(
    api_key: str = Depends(verify_api_key),
    session: DBSession = Depends(get_session),
):
    user = get_display_name(api_key, session)
    logger.info(f"History request from user: {user}")

    jobs = session.exec(
        select(Job).where(Job.user_id == api_key)
        .order_by(Job.created_at.desc())
        .limit(settings.max_queries_per_user)
    ).all()

    history = [json.loads(j.input_json) for j in jobs]
    count = len(jobs)

    logger.info(f"Returning {count} submissions for user: {user}")

    return {
        "user": user,
        "total_submissions": count,
        "history": history,
    }
