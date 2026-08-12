from fastapi import Header, HTTPException, Depends
from typing import Dict, List
from collections import deque
import logging
import time
import threading

from .settings import settings
from .db import (
    load_users,
    get_valid_api_keys as db_get_valid_api_keys,
    get_all_leaderboard_entries,
    insert_leaderboard_entry,
    input_exists_in_leaderboard,
    trim_leaderboard,
)

from .task_loader import load_active_task
# Note: job_manager is imported elsewhere (main.py) which ensures jobs + quota state are initialized.


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MAX_QUERIES_PER_USER = settings.max_queries_per_user
LEADERBOARD_SIZE = settings.leaderboard_size


def get_display_name(api_key: str) -> str:
    return load_users().get(api_key, "Anonymous")

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

_leaderboard_lock = threading.RLock()


def _get_task_info():
    try:
        task = load_active_task()
        minimize = getattr(task, "MINIMIZE", True)
    except Exception:
        minimize = True
    return settings.active_task, minimize


def add_to_leaderboard(user_id: str, input: dict, score: float, solved: bool):
    with _leaderboard_lock:
        task_name, minimize = _get_task_info()

        if input_exists_in_leaderboard(task_name, input):
            logger.info(f"Duplicate solution submitted by {get_display_name(user_id)}, ignoring.")
            return None

        insert_leaderboard_entry(user_id, task_name, input, score, solved, time.time())
        trim_leaderboard(task_name, LEADERBOARD_SIZE, minimize)

        entries = get_all_leaderboard_entries(task_name)
        entries.sort(key=lambda x: x["score"], reverse=not minimize)

        display_name = get_display_name(user_id)
        logger.info(f"Leaderboard updated. User: {display_name}, Score: {score:.6f}, Total entries: {len(entries)}")

        rank = None
        for i, e in enumerate(entries, 1):
            if e["user_id"] == user_id and e["score"] == score:
                rank = i
                break

    return rank


def get_leaderboard() -> List[dict]:
    task_name, minimize = _get_task_info()

    entries = get_all_leaderboard_entries(task_name)
    entries.sort(key=lambda x: x["score"], reverse=not minimize)
    return [
        {
            "user": get_display_name(e["user_id"]),
            "input": e["input"],
            "score": e["score"],
            "solved": e["solved"],
            "timestamp": e["timestamp"],
        }
        for e in entries
    ]

async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in db_get_valid_api_keys():
        logger.warning("Invalid API key attempted")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def get_tracker() -> UserSubmissionTracker:
    return user_tracker
