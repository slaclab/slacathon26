import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import logging

from app.settings import settings
from app.core.task_loader import load_active_task
from app.routers import jobs, leaderboard, registration
from app.db import create_db_and_tables

logger = logging.getLogger(__name__)

app = FastAPI(root_path=settings.root_path)

templates = Jinja2Templates(directory="app/templates")

# Load task at startup (validates config and populates quota limits)
TASK = load_active_task()
logger.info(f"Loaded task: {getattr(TASK, 'TASK_NAME', 'Unknown')}")

app.include_router(jobs.router)
app.include_router(leaderboard.router)
app.include_router(registration.router)


@app.on_event("startup")
async def on_startup():
    create_db_and_tables()
    asyncio.create_task(_cleanup_loop())


async def _cleanup_loop():
    import logging
    from datetime import datetime
    from sqlmodel import Session, select
    from app.db import engine
    from app.models.user import User
    from app.settings import settings
    logger = logging.getLogger(__name__)
    interval = settings.cleanup_interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        try:
            with Session(engine) as session:
                expired = session.exec(
                    select(User).where(User.verified == False, User.expires_at < datetime.utcnow())
                ).all()
                for u in expired:
                    session.delete(u)
                session.commit()
                if expired:
                    logger.info(f"Cleanup: removed {len(expired)} expired unverified users")
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    logger.info("Root endpoint accessed")
    return templates.TemplateResponse("pages/index.html", {"request": request})


@app.get("/board", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    logger.info("Leaderboard page accessed")
    return templates.TemplateResponse("pages/leaderboard.html", {"request": request})


@app.get("/team", response_class=HTMLResponse)
async def team_page(request: Request):
    logger.info("Team page accessed")
    return templates.TemplateResponse("pages/team.html", {"request": request})


@app.get("/health")
async def health():
    logger.debug("Health check accessed")
    return {"status": "rockin' and rollin'"}


@app.get("/america")
async def america():
    logger.info("America endpoint accessed - redirecting")
    return RedirectResponse("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
