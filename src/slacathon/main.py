from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.responses import RedirectResponse, HTMLResponse
from .task_loader import load_active_task
from .middleware import (
    verify_api_key, 
    get_tracker, 
    UserSubmissionTracker, 
    add_to_leaderboard,
    get_leaderboard,
    get_display_name,
)
from .job_manager import (
    create_job,
    get_job,
    complete_job,
    make_json_safe,
    charge_validation_quota,
    get_quota_info,
)
import asyncio
import logging
import time

from .settings import settings
from pathlib import Path

logger = logging.getLogger(__name__)

app = FastAPI(root_path=settings.root_path)

TASK = load_active_task()
logger.info(f"Loaded task: {getattr(TASK, 'TASK_NAME', 'Unknown')}")

landing_page_html = (Path(__file__).resolve().parent.parent.parent / "web/index.html").read_text()
leaderboard_page_html = (Path(__file__).resolve().parent.parent.parent / "web/leaderboard.html").read_text()
team_page_html = (Path(__file__).resolve().parent.parent.parent / "web/team.html").read_text()


def _extract_input_data(body: dict) -> dict:
    """Shared helper to extract input from either {"input": <obj>} or flat object.
    Supports both wrapped and direct input formats used by clients.
    """
    if "input" in body:
        return body["input"]
    return body


@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return HTMLResponse(content=landing_page_html, status_code=200)

@app.get("/board")
async def leaderboard_page():
    logger.info("Leaderboard page accessed")
    return HTMLResponse(content=leaderboard_page_html, status_code=200)

@app.get("/health")
async def health():
    logger.debug("Health check accessed")
    return {"status": "rockin' and rollin'"}


@app.get("/task")
async def get_task_info():
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

@app.get("/team")
async def team_page():
    logger.info("Team page accessed")
    return HTMLResponse(content=team_page_html, status_code=200)

@app.get("/america")
async def america():
    logger.info("America endpoint accessed - redirecting")
    return RedirectResponse("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


@app.get("/history")
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

@app.get("/leaderboard")
async def view_leaderboard():
    logger.info("Leaderboard API request received")
    board = get_leaderboard()
    
    return {
        "total_entries": len(board),
        "leaderboard": board
    }

@app.post("/submit")
async def submit_result(
    body: dict = Body(...),
    api_key: str = Depends(verify_api_key)
):
    input_data = _extract_input_data(body)
    logger.info(f"Leaderboard submission from user: {get_display_name(api_key)}")
    logger.info(f"Submitted input: {input_data}")
    
    try:
        # charge via single primitive: minimal record for submit path (persisted, counted on restart)
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
            solved=result['solved']
        )
        
        board = get_leaderboard()
        display_name = get_display_name(api_key)
        
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

async def run_validation_job(job_id: str, input_data: dict):
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

@app.post("/validate")
async def validate(
    body: dict = Body(...),
    api_key: str = Depends(verify_api_key),
    tracker: UserSubmissionTracker = Depends(get_tracker)
):
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


@app.get("/jobs/{job_id}")
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



