# Phase 07 — Migrate Auth & Display Name to DB

## Scope
Update `app/core/middleware.py` to:
1. Replace env-var API key lookup with DB query
2. Replace `user_names.json` / dict lookup with DB query
3. Update `add_to_leaderboard` to snapshot display name at write time
4. Update `LeaderboardEntry` to carry `display_name`
5. Remove: `_load_valid_api_keys`, `VALID_API_KEYS`, `user_names_fallback`, `load_user_names`, `save_user_names`, `user_names`, `USER_NAMES_FILE`

`settings.py`: remove `user_names_file` field (only used in middleware).
`data/user_names.json` still on disk but no longer read — can be deleted separately.

## Prereq
Phases 01–06 complete (DB has verified users, dev seed runs on startup).

## Files Modified
| File | Change |
|---|---|
| `app/core/middleware.py` | Replace key auth + display name resolution |
| `app/settings.py` | Remove `user_names_file` field |

---

## middleware.py — key changes

### Remove entirely
```python
# DELETE these
def _load_valid_api_keys() -> set: ...
VALID_API_KEYS = _load_valid_api_keys()
user_names_fallback = {...}
def load_user_names() -> Dict[str, str]: ...
def save_user_names(names: Dict[str, str]): ...
user_names = load_user_names()
USER_NAMES_FILE = settings.user_names_file
```

### Replace `verify_api_key`
```python
# Before
async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

# After
from sqlmodel import Session as DBSession, select as db_select
from app.db import get_session
from app.models.user import User

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
```

### Replace `get_display_name`
```python
# Before
def get_display_name(api_key: str) -> str:
    return user_names.get(api_key, "Anonymous")

# After
def get_display_name(api_key: str, session: DBSession) -> str:
    user = session.exec(db_select(User).where(User.api_key == api_key)).first()
    return user.display_name if user else "Anonymous"
```

### Update `LeaderboardEntry`
```python
class LeaderboardEntry:
    def __init__(self, user_id: str, display_name: str, input: dict, score: float, solved: bool, timestamp: float):
        self.user_id = user_id
        self.display_name = display_name   # ← new: snapshot at write time
        self.input = input
        self.score = score
        self.solved = solved
        self.timestamp = timestamp

    def to_dict(self):
        return {
            "user": self.display_name,     # ← use snapshot, no DB needed at read time
            "input": self.input,
            "score": self.score,
            "solved": self.solved,
            "timestamp": self.timestamp
        }

    def to_storage_dict(self):
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,   # ← persist snapshot
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
            display_name=data.get("display_name", "Anonymous"),   # ← backward compat with old JSON
            input=inp,
            score=data["score"],
            solved=data["solved"],
            timestamp=data["timestamp"]
        )
```

### Update `add_to_leaderboard`
```python
def add_to_leaderboard(user_id: str, input: dict, score: float, solved: bool, session: DBSession):
    global leaderboard
    ...
    display_name = get_display_name(user_id, session)
    entry = LeaderboardEntry(user_id, display_name, input, score, solved, time.time())
    ...
```

### Callers of `add_to_leaderboard` in `app/routers/jobs.py`
Must pass `session` as new arg. The router already has `session` from `Depends(get_session)`.

---

## settings.py change

Remove:
```python
user_names_file: str = Field(default="data/user_names.json")
```

---

## Acceptance Criteria
- `GET /slacathon26/health` → 200
- `POST /validate` with `X-API-Key: key_123` → not 401 (dev seed user exists)
- `POST /validate` with `X-API-Key: badkey` → 401
- Leaderboard entries have `user` field populated from DB display name
- `data/user_names.json` can be deleted without affecting anything

---

## Test Suite: `tests/test_phase07_middleware_db_auth.py`

```python
"""Phase 07 — DB-backed API key auth and display name resolution."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session, SQLModel, create_engine, select
from unittest.mock import patch


@pytest.fixture(scope="module")
def mem_engine():
    from app.models.user import User  # noqa
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    # Insert test users
    with Session(eng) as s:
        from app.models.user import User
        s.add(User(email="a@t.com", display_name="Alice", api_key="good_key",
                   verified=True, verify_token="t1"))
        s.add(User(email="b@t.com", display_name="Bob", api_key="unverified_key",
                   verified=False, verify_token="t2"))
        s.commit()
    return eng


@pytest.fixture(scope="module")
def client(mem_engine):
    from app.core.middleware import verify_api_key
    from app.db import get_session

    app = FastAPI()

    def override_session():
        with Session(mem_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session

    @app.get("/test-auth")
    async def test_auth(api_key: str = Depends(verify_api_key)):
        return {"key": api_key}

    return TestClient(app)


def test_valid_key_passes(client):
    resp = client.get("/test-auth", headers={"x-api-key": "good_key"})
    assert resp.status_code == 200
    assert resp.json()["key"] == "good_key"


def test_invalid_key_rejected(client):
    resp = client.get("/test-auth", headers={"x-api-key": "bad_key"})
    assert resp.status_code == 401


def test_unverified_key_rejected(client):
    resp = client.get("/test-auth", headers={"x-api-key": "unverified_key"})
    assert resp.status_code == 401


def test_get_display_name(mem_engine):
    from app.core.middleware import get_display_name
    with Session(mem_engine) as s:
        assert get_display_name("good_key", s) == "Alice"


def test_get_display_name_unknown(mem_engine):
    from app.core.middleware import get_display_name
    with Session(mem_engine) as s:
        assert get_display_name("no_such_key", s) == "Anonymous"


def test_leaderboard_entry_display_name_snapshot():
    from app.core.middleware import LeaderboardEntry
    e = LeaderboardEntry("uid1", "Alice", {"q1": 0.1}, 0.5, False, 1000.0)
    d = e.to_dict()
    assert d["user"] == "Alice"


def test_leaderboard_entry_from_dict_compat():
    """Old JSON without display_name field must load as Anonymous."""
    from app.core.middleware import LeaderboardEntry
    old_record = {"user_id": "uid1", "input": {}, "score": 0.5, "solved": False, "timestamp": 1000.0}
    e = LeaderboardEntry.from_dict(old_record)
    assert e.display_name == "Anonymous"


def test_add_to_leaderboard_with_session(mem_engine):
    from app.core.middleware import add_to_leaderboard, get_leaderboard
    with Session(mem_engine) as s:
        rank = add_to_leaderboard("good_key", {"q1": 0.2}, 0.42, False, s)
    board = get_leaderboard()
    assert any(e["user"] == "Alice" for e in board)
```
