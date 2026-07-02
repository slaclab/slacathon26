from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import logging

from app.settings import settings
from app.core.task_loader import load_active_task
from app.routers import jobs, leaderboard

logger = logging.getLogger(__name__)

app = FastAPI(root_path=settings.root_path)

templates = Jinja2Templates(directory="app/templates")

# Load task at startup (validates config and populates quota limits)
TASK = load_active_task()
logger.info(f"Loaded task: {getattr(TASK, 'TASK_NAME', 'Unknown')}")

app.include_router(jobs.router)
app.include_router(leaderboard.router)


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
