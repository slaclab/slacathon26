from fastapi import Header, HTTPException, Depends
from typing import Dict, List
from collections import deque
import logging
import time
import json
import os
import uuid
import threading
import numpy as np


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to get labels for legacy list->dict normalization of old leaderboard data
_TASK_INPUT_LABELS = None
try:
    from task_loader import load_active_task
    _TASK_INPUT_LABELS = getattr(load_active_task(), "INPUT_LABELS", None)
except Exception:
    pass

MAX_QUERIES_PER_USER = 10
MAX_VALIDATIONS_PER_USER = 10000
LEADERBOARD_SIZE = 15
LEADERBOARD_FILE = "leaderboard.json"
USER_NAMES_FILE = "user_names.json"

user_validation_counts: Dict[str, int] = {}


def consume_validation_quota(user_id: str) -> int:
    current = user_validation_counts.get(user_id, 0)
    if current >= MAX_VALIDATIONS_PER_USER:
        raise RuntimeError(
            f"Validation limit of {MAX_VALIDATIONS_PER_USER} reached for this API key"
        )
    user_validation_counts[user_id] = current + 1
    return MAX_VALIDATIONS_PER_USER - (current + 1)

def _load_valid_api_keys() -> set:
    env_keys = os.environ.get("SLACATHON_API_KEYS")
    if env_keys:
        keys = {k.strip() for k in env_keys.replace(",", " ").split() if k.strip()}
        if keys:
            logger.info(f"Loaded {len(keys)} API key(s) from SLACATHON_API_KEYS environment variable")
            return keys

    logger.warning(
        "SLACATHON_API_KEYS not set. Using hardcoded development keys. "
        "This is insecure — set the environment variable for any real use."
    )
    return {"key_123", "key_456", "key_789"}


VALID_API_KEYS = _load_valid_api_keys()

user_names_fallback = {
    "key_123": "Alex",
    "key_456": "Chris",
    "key_789": "Ken",
}

def load_user_names() -> Dict[str, str]:
    if os.path.exists(USER_NAMES_FILE):
        try:
            with open(USER_NAMES_FILE, 'r') as f:
                names = json.load(f)
                logger.info(f"Loaded {len(names)} user names from file")
                return names
        except Exception as e:
            logger.error(f"Failed to load user names: {e}")
            return user_names_fallback.copy()
    else:
        save_user_names(user_names_fallback)
        return user_names_fallback.copy()

def save_user_names(names: Dict[str, str]):
    try:
        with open(USER_NAMES_FILE, 'w') as f:
            json.dump(names, f, indent=2)
        logger.info(f"Saved {len(names)} user names to file")
    except Exception as e:
        logger.error(f"Failed to save user names: {e}")

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
        inp = data.get("input")
        if inp is None:
            inp = data.get("values", {})
        # Normalize legacy array inputs to dict using current task labels
        if isinstance(inp, list) and _TASK_INPUT_LABELS and len(inp) == len(_TASK_INPUT_LABELS):
            inp = {label: val for label, val in zip(_TASK_INPUT_LABELS, inp)}
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

JOBS_FILE = "jobs.json"
jobs: dict = {}
jobs_lock = threading.RLock()
append_lock = threading.Lock()

def load_jobs():
    global jobs
    jobs = {}
    if not os.path.exists(JOBS_FILE):
        logger.info("No existing jobs file found, starting fresh")
        return
    try:
        with open(JOBS_FILE, 'r') as f:
            lines = f.readlines()
        recent_lines = lines[-300:]
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
                if isinstance(job, dict) and "job_id" in job:
                    if "input" not in job and "values" in job:
                        job["input"] = job.pop("values")
                    jobs[job["job_id"]] = job
            except Exception:
                continue
        logger.info(f"Loaded {len(jobs)} recent jobs into memory (full history kept in the file)")

        global user_validation_counts
        user_validation_counts = {}
        try:
            with open(JOBS_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        job = json.loads(line)
                        uid = job.get("user_id")
                        if uid:
                            user_validation_counts[uid] = user_validation_counts.get(uid, 0) + 1
                    except Exception:
                        continue
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Failed to load jobs: {e}")
        jobs = {}

def _append_job_record(job_record: dict):
    try:
        with append_lock:
            with open(JOBS_FILE, "a") as f:
                f.write(json.dumps(job_record) + "\n")
    except Exception as e:
        logger.error(f"Failed to append job record: {e}")

def get_job(job_id: str) -> dict | None:
    with jobs_lock:
        if job_id in jobs:
            return jobs[job_id]
    try:
        with open(JOBS_FILE, 'r') as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("job_id") == job_id:
                    if "input" not in rec and "values" in rec:
                        rec["input"] = rec.pop("values")
                    with jobs_lock:
                        jobs[job_id] = rec
                    return rec
            except Exception:
                continue
    except Exception:
        pass
    return None

load_jobs()

def create_job(user_id: str, input_data: dict) -> str:
    remaining_after = consume_validation_quota(user_id)

    job_id = str(uuid.uuid4())
    job_record = {
        "job_id": job_id,
        "user_id": user_id,
        "input": input_data,
        "status": "processing",
        "result": None,
        "created_at": time.time(),
        "completed_at": None
    }
    with jobs_lock:
        jobs[job_id] = job_record
    _append_job_record(job_record)

    logger.info(f"Created job {job_id} for user {get_display_name(user_id)} "
                f"(used {MAX_VALIDATIONS_PER_USER - remaining_after}/{MAX_VALIDATIONS_PER_USER})")
    return job_id

def make_json_safe(obj):
    import math
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer, np.floating)):
        val = float(obj)
        if not math.isfinite(val):
            return 1.0e10
        return val
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return 1.0e10
        return obj
    return obj

def complete_job(job_id: str, result: dict):
    safe_result = make_json_safe(result)
    job_record = None
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = safe_result
            jobs[job_id]["completed_at"] = time.time()
            job_record = dict(jobs[job_id])
    if job_record:
        _append_job_record(job_record)
        logger.info(f"Job {job_id} completed with score {safe_result.get('score')}")


def add_to_leaderboard(user_id: str, input: dict, score: float, solved: bool):
    global leaderboard

    for existing in leaderboard:
        if existing.input == input:
            logger.info(f"Duplicate solution submitted by {get_display_name(user_id)}, ignoring.")
            return

    entry = LeaderboardEntry(user_id, input, score, solved, time.time())
    leaderboard.append(entry)
    
    leaderboard.sort(key=lambda x: x.score)
    leaderboard = leaderboard[:LEADERBOARD_SIZE]
    
    display_name = get_display_name(user_id)
    logger.info(f"Leaderboard updated. User: {display_name}, Score: {score:.6f}, Total entries: {len(leaderboard)}")
    save_leaderboard()

def get_leaderboard() -> List[dict]:
    return [entry.to_dict() for entry in leaderboard]

async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        logger.warning("Invalid API key attempted")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def get_tracker() -> UserSubmissionTracker:
    return user_tracker
