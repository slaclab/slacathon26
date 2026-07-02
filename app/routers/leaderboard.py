from fastapi import APIRouter
from fastapi.responses import RedirectResponse
import logging

from app.core.middleware import get_leaderboard, get_display_name, verify_api_key, get_tracker, UserSubmissionTracker
from app.core.task_loader import load_active_task
from fastapi import Depends

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/leaderboard")
async def view_leaderboard():
    logger.info("Leaderboard API request received")
    board = get_leaderboard()
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
    tracker: UserSubmissionTracker = Depends(get_tracker)
):
    user = get_display_name(api_key)
    logger.info(f"History request from user: {user}")

    history = tracker.get_recent_submissions(api_key)
    count = tracker.get_submission_count(api_key)

    logger.info(f"Returning {count} submissions for user: {user}")

    return {
        "user": user,
        "total_submissions": count,
        "history": history
    }
