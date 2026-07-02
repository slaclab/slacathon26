from fastapi import Header, HTTPException, Depends
from sqlmodel import Session as DBSession, select as db_select
from typing import Dict, List
from collections import deque
import logging
import time
import json
import os
import threading
import numpy as np

from app.settings import settings
from app.core.task_loader import load_active_task
from app.db import get_session
from app.models.user import User


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MAX_QUERIES_PER_USER = settings.max_queries_per_user
LEADERBOARD_SIZE = settings.leaderboard_size
LEADERBOARD_FILE = settings.leaderboard_file


def get_display_name(api_key: str, session: DBSession) -> str:
    user = session.exec(db_select(User).where(User.api_key == api_key)).first()
    return user.display_name if user else "Anonymous"

class LeaderboardEntry:
    def __init__(self, user_id: str, display_name: str, input: dict, score: float, solved: bool, timestamp: float):
        self.user_id = user_id
        self.display_name = display_name
        self.input = input
        self.score = score
        self.solved = solved
        self.timestamp = timestamp

    def to_dict(self):
        return {
            "user": self.display_name,
            "input": self.input,
            "score": self.score,
            "solved": self.solved,
            "timestamp": self.timestamp
        }

    def to_storage_dict(self):
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "input": self.input,
            "score": self.score,
            "solved": self.solved,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: dict):
        inp = data.get("input", {})
        if not isinstance(inp, dict):
            inp = {}
        return cls(
            user_id=data["user_id"],
            display_name=data.get("display_name", "Anonymous"),
            input=inp,
            score=data["score"],
            solved=data["solved"],
            timestamp=data["timestamp"]
        )

def load_leaderboard() -> List[LeaderboardEntry]:
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, 'r') as f:
                data = json.load(f)
                entries = [LeaderboardEntry.from_dict(entry) for entry in data]
                logger.info(f"Loaded {len(entries)} entries from leaderboard file")
                return entries
        except Exception as e:
            logger.error(f"Failed to load leaderboard: {e}")
            return []
    else:
        logger.info("No existing leaderboard file found, starting fresh")
        return []

def save_leaderboard():
    try:
        data = [entry.to_storage_dict() for entry in leaderboard]
        with open(LEADERBOARD_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(leaderboard)} entries to leaderboard file")
    except Exception as e:
        logger.error(f"Failed to save leaderboard: {e}")

leaderboard = load_leaderboard()

class UserSubmissionTracker:
    def __init__(self, max_queries: int):
        self.max_queries = max_queries
        self.submissions: Dict[str, deque] = {}
        logger.info(f"UserSubmissionTracker initialized with max {max_queries} entries per user")

    def add_submission(self, user_id: str, input_data: dict):
        if user_id not in self.submissions:
            self.submissions[user_id] = deque(maxlen=self.max_queries)
        self.submissions[user_id].append(input_data)

    def get_recent_submissions(self, user_id: str) -> List[dict]:
        return list(self.submissions.get(user_id, []))

    def get_submission_count(self, user_id: str) -> int:
        return len(self.submissions.get(user_id, []))

user_tracker = UserSubmissionTracker(MAX_QUERIES_PER_USER)


def add_to_leaderboard(user_id: str, input: dict, score: float, solved: bool, session: DBSession):
    global leaderboard

    display_name = get_display_name(user_id, session)

    for existing in leaderboard:
        if existing.input == input:
            logger.info(f"Duplicate solution submitted by {display_name}, ignoring.")
            return None

    entry = LeaderboardEntry(user_id, display_name, input, score, solved, time.time())
    leaderboard.append(entry)

    try:
        task = load_active_task()
        minimize = getattr(task, "MINIMIZE", True)
    except Exception:
        minimize = True
    leaderboard.sort(key=lambda x: x.score, reverse=not minimize)
    leaderboard = leaderboard[:LEADERBOARD_SIZE]

    logger.info(f"Leaderboard updated. User: {display_name}, Score: {score:.6f}, Total entries: {len(leaderboard)}")
    save_leaderboard()

    for i, e in enumerate(leaderboard, 1):
        if e is entry:
            return i
    return None

def get_leaderboard() -> List[dict]:
    return [entry.to_dict() for entry in leaderboard]

async def verify_api_key(
    x_api_key: str = Header(...),
    session: DBSession = Depends(get_session),
) -> str:
    user = session.exec(
        db_select(User).where(User.api_key == x_api_key, User.verified == True)
    ).first()
    if not user:
        logger.warning("Invalid or unverified API key attempted")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def get_tracker() -> UserSubmissionTracker:
    return user_tracker
