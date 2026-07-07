import json
import logging
import time

from fastapi import Header, HTTPException, Depends
from sqlmodel import Session as DBSession, select as db_select

from app.settings import settings
from app.db import get_session
from app.models.user import User
from app.models.leaderboard_entry import LeaderboardEntry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

LEADERBOARD_SIZE = settings.leaderboard_size


def get_display_name(api_key: str, session: DBSession) -> str:
    user = session.exec(db_select(User).where(User.api_key == api_key)).first()
    return user.display_name if user else "Anonymous"


def add_to_leaderboard(user_id: str, input: dict, score: float, solved: bool, session: DBSession) -> int | None:
    display_name = get_display_name(user_id, session)

    input_json = json.dumps(input, sort_keys=True)
    existing = session.exec(
        db_select(LeaderboardEntry).where(LeaderboardEntry.input_json == input_json)
    ).first()
    if existing:
        logger.info(f"Duplicate solution submitted by {display_name}, ignoring.")
        return None

    entry = LeaderboardEntry(
        user_id=user_id,
        display_name=display_name,
        input_json=input_json,
        score=score,
        solved=solved,
        timestamp=time.time(),
    )
    session.add(entry)
    session.commit()

    from app.core.task_loader import load_active_task
    try:
        task = load_active_task()
        minimize = getattr(task, "MINIMIZE", True)
    except Exception:
        minimize = True

    if minimize:
        rank = session.exec(
            db_select(LeaderboardEntry).where(LeaderboardEntry.score <= score)
        ).all()
    else:
        rank = session.exec(
            db_select(LeaderboardEntry).where(LeaderboardEntry.score >= score)
        ).all()

    logger.info(f"Leaderboard updated. User: {display_name}, Score: {score:.6f}")
    return len(rank)


def get_leaderboard(session: DBSession) -> list[dict]:
    from app.core.task_loader import load_active_task
    try:
        task = load_active_task()
        minimize = getattr(task, "MINIMIZE", True)
    except Exception:
        minimize = True

    all_entries = session.exec(db_select(LeaderboardEntry)).all()
    all_entries.sort(key=lambda e: e.score, reverse=not minimize)
    entries = all_entries[:LEADERBOARD_SIZE]
    return [
        {
            "user": e.display_name,
            "input": json.loads(e.input_json),
            "score": e.score,
            "solved": e.solved,
            "timestamp": e.timestamp,
        }
        for e in entries
    ]


async def verify_api_key(
    x_api_key: str = Header(...),
    session: DBSession = Depends(get_session),
) -> str:
    user = session.exec(
        db_select(User).where(User.api_key == x_api_key, User.verified == True)  # noqa: E712
    ).first()
    if not user:
        logger.warning("Invalid or unverified API key attempted")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
