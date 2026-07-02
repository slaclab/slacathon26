from fastapi import APIRouter, HTTPException, Depends, Body
import asyncio
import logging
import time

from app.core.middleware import verify_api_key, get_tracker, UserSubmissionTracker, get_display_name
from app.db import get_session
from sqlmodel import Session as DBSession
from app.core.job_manager import (
    create_job,
    get_job,
    complete_job,
    make_json_safe,
    charge_validation_quota,
    get_quota_info,
)
from app.core.task_loader import load_active_task

router = APIRouter()
logger = logging.getLogger(__name__)


def _extract_input_data(body: dict) -> dict:
    if "input" in body:
        return body["input"]
    return body


async def run_validation_job(job_id: str, input_data: dict):
    TASK = load_active_task()
    try:
        logger.info(f"Background job {job_id} starting heavy validation...")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda d: TASK.validate(d).model_dump(), input_data)
        logger.info(f"Background job {job_id} computation done, applying delay...")
        await asyncio.sleep(1.0)
        complete_job(job_id, result)
        logger.info(f"Background job {job_id} finished and result stored.")
    except Exception as e:
        logger.error(f"Background job {job_id} failed: {e}", exc_info=True)
        job = get_job(job_id)
        if job:
            complete_job(job_id, {
                "solved": False,
                "score": getattr(TASK, "FAILURE_SCORE", 1.0e10),
                "message": f"Job failed: {str(e)}",
                "evaltime": 0.0
            })


@router.post("/validate")
async def validate(
    body: dict = Body(...),
    api_key: str = Depends(verify_api_key),
    tracker: UserSubmissionTracker = Depends(get_tracker)
):
    TASK = load_active_task()
    input_data = _extract_input_data(body)
    logger.info(f"Validation job request received from user: {get_display_name(api_key)}")
    logger.info(f"Submitted input: {input_data}")

    try:
        if isinstance(input_data, dict):
            TASK.Input(**input_data)

        tracker.add_submission(api_key, input_data)

        job_id = create_job(api_key, input_data)

        asyncio.create_task(run_validation_job(job_id, input_data))

        logger.info(f"Validation job {job_id} enqueued for user {get_display_name(api_key)}")

        return {
            "job_id": job_id,
            "status": "processing",
            "message": "Submission recorded. Validation is running in the background (this can take time). Poll GET /jobs/{job_id} to retrieve the result when ready.",
            "quota": get_quota_info(api_key)
        }
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Validation job creation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start validation job")


@router.post("/submit")
async def submit_result(
    body: dict = Body(...),
    api_key: str = Depends(verify_api_key),
    session: DBSession = Depends(get_session),
):
    from app.core.middleware import add_to_leaderboard, get_leaderboard
    TASK = load_active_task()
    input_data = _extract_input_data(body)
    logger.info(f"Leaderboard submission from user: {get_display_name(api_key, session)}")
    logger.info(f"Submitted input: {input_data}")

    try:
        charge_validation_quota(
            api_key,
            record={"user_id": api_key, "kind": "submit", "created_at": time.time()}
        )

        validated_input = TASK.Input(**input_data)
        result = TASK.validate(validated_input).model_dump()
        logger.info(f"Evaluation result: {result}")

        rank = add_to_leaderboard(
            user_id=api_key,
            input=input_data,
            score=result['score'],
            solved=result['solved'],
            session=session,
        )

        board = get_leaderboard()
        display_name = get_display_name(api_key, session)

        return {
            "submitted": True,
            "user": display_name,
            "score": result['score'],
            "solved": result['solved'],
            "message": result['message'],
            "rank": rank,
            "leaderboard_size": len(board)
        }

    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.error(f"Submission error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while processing submission")


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    api_key: str = Depends(verify_api_key)
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("user_id") != api_key:
        raise HTTPException(status_code=403, detail="This job belongs to another user")

    response = {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "input": job.get("input"),
    }

    if job["status"] == "completed" and job.get("result"):
        response["result"] = make_json_safe(job["result"])
        response["completed_at"] = job.get("completed_at")

    response["quota"] = get_quota_info(api_key)

    return response
