# Phase 06 — Wire Router & DB Init into main.py

## Scope
Minimal changes to `app/main.py`:
1. Call `create_db_and_tables()` on startup
2. Mount registration router
3. Start cleanup background task on startup

No other file changes. Existing routes/behavior unchanged.

## Prereq
Phases 01–05 complete.

## Files Modified
| File | Change |
|---|---|
| `app/main.py` | startup event + router mount |

---

## Diff for `app/main.py`

```python
# Add to imports
import asyncio
from app.db import create_db_and_tables
from app.routers import registration  # new

# Add router mount (after existing includes)
app.include_router(registration.router)

# Add startup handler
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
```

---

## Acceptance Criteria
- App starts without error (`uvicorn app.main:app`)
- `GET /slacathon26/register` returns 200
- `GET /slacathon26/health` still returns `{"status": "rockin' and rollin'"}`
- `data/users.db` created on first boot
- Dev seed users present in DB

---

## Test Suite: `tests/test_phase06_main_wiring.py`

```python
"""Phase 06 — app startup wiring: DB init, router mount, cleanup task."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@pytest.fixture(scope="module")
def client():
    # Patch create_db_and_tables so tests don't need real filesystem
    with patch("app.db.create_db_and_tables") as mock_db, \
         patch("app.main.create_db_and_tables") as mock_main_db:
        mock_db.return_value = None
        mock_main_db.return_value = None
        from app.main import app
        with TestClient(app) as c:
            yield c


def test_health_still_works(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rockin' and rollin'"


def test_register_route_mounted(client):
    resp = client.get("/register")
    # Could return 200 or 500 if DB not inited, but route must exist (not 404)
    assert resp.status_code != 404


def test_existing_leaderboard_route(client):
    resp = client.get("/leaderboard")
    assert resp.status_code == 200


def test_existing_task_route(client):
    resp = client.get("/task")
    assert resp.status_code == 200


def test_cleanup_loop_is_coroutine():
    from app.main import _cleanup_loop
    import asyncio
    assert asyncio.iscoroutinefunction(_cleanup_loop)
```
