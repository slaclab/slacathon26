from fastapi import Header, HTTPException, Depends
from typing import Dict, List
from collections import deque
import logging
import time
import json
import os
import threading

from .settings import settings
from .db import init_db, load_users, get_valid_api_keys as db_get_valid_api_keys, upsert_user

from .task_loader import load_active_task
# Note: job_manager is imported elsewhere (main.py) which ensures jobs + quota state are initialized.


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MAX_QUERIES_PER_USER = settings.max_queries_per_user
LEADERBOARD_SIZE = settings.leaderboard_size
LEADERBOARD_FILE = settings.leaderboard_file

leaderboard_lock = threading.RLock()

def _load_valid_api_keys() -> set:
    init_db()
    keys = set()
    if settings.api_keys:
        keys = set(settings.api_keys)
        logger.info(f"Loaded {len(keys)} API key(s) from settings")

    db_keys = db_get_valid_api_keys()
    if db_keys:
        keys |= db_keys
        logger.info(f"Loaded {len(db_keys)} API key(s) from database")

    if not keys:
        logger.warning(
            "No API keys configured in settings. Using hardcoded development keys. "
            "This is insecure — set SLACATHON_API_KEYS in your environment."
        )
        keys = {"key_123", "key_456", "key_789"}
    return keys


VALID_API_KEYS = _load_valid_api_keys()


def load_user_names() -> Dict[str, str]:
    """Load user names from the database (post-migration)."""
    init_db()
    names = load_users() or {}
    if names:
        logger.info(f"Loaded {len(names)} user names from database")
    return names


user_names = load_user_names()

def get_display_name(api_key: str) -> str:
    return user_names.get(api_key, "Anonymous")

class LeaderboardEntry:
    def __init__(self, user_id: str, input: dict, score: float, solved: bool, timestamp: float):
        self.user_id = user_id
        self.input = input
        self.score = score
        self.solved = solved
        self.timestamp = timestamp
    
    def to_dict(self):
        return {
            "user": get_display_name(self.user_id),
            "input": self.input,
            "score": self.score,
            "solved": self.solved,
            "timestamp": self.timestamp
        }
    
    def to_storage_dict(self):
        return {
            "user_id": self.user_id,
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

def _atomic_save_leaderboard(data):
    """Write leaderboard data atomically to prevent corruption on concurrent writes."""
    try:
        tmp_path = LEADERBOARD_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, LEADERBOARD_FILE)
        logger.info(f"Saved {len(data)} entries to leaderboard file")
    except Exception as e:
        logger.error(f"Failed to save leaderboard: {e}")

with leaderboard_lock:
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


def add_to_leaderboard(user_id: str, input: dict, score: float, solved: bool):
    global leaderboard

    with leaderboard_lock:
        for existing in leaderboard:
            if existing.input == input:
                logger.info(f"Duplicate solution submitted by {get_display_name(user_id)}, ignoring.")
                return None

        entry = LeaderboardEntry(user_id, input, score, solved, time.time())
        leaderboard.append(entry)
        
        # Sort respecting task direction (lower better if minimize)
        try:
            task = load_active_task()
            minimize = getattr(task, "MINIMIZE", True)
        except Exception:
            minimize = True
        leaderboard.sort(key=lambda x: x.score, reverse=not minimize)
        leaderboard = leaderboard[:LEADERBOARD_SIZE]
        
        display_name = get_display_name(user_id)
        logger.info(f"Leaderboard updated. User: {display_name}, Score: {score:.6f}, Total entries: {len(leaderboard)}")
        
        # Compute rank while still holding the lock (so 'is entry' is reliable)
        rank = None
        for i, e in enumerate(leaderboard, 1):
            if e is entry:
                rank = i
                break

        # Snapshot data for save (still under lock)
        data_to_save = [entry.to_storage_dict() for entry in leaderboard]

    # Save outside the lock to avoid holding it during I/O
    _atomic_save_leaderboard(data_to_save)

    return rank

def get_leaderboard() -> List[dict]:
    with leaderboard_lock:
        return [entry.to_dict() for entry in leaderboard]

async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        logger.warning("Invalid API key attempted")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def get_tracker() -> UserSubmissionTracker:
    return user_tracker
