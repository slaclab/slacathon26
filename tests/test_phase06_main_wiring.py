"""Phase 06 — app startup wiring: DB init, router mount, cleanup task."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from unittest.mock import patch, AsyncMock


@pytest.fixture(scope="module")
def client():
    from sqlalchemy.pool import StaticPool
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from app.models.user import User  # noqa: F401
    from app.models.job import Job  # noqa: F401
    from app.models.leaderboard_entry import LeaderboardEntry  # noqa: F401
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    with patch("app.db.create_db_and_tables"), \
         patch("app.main.create_db_and_tables"):
        from app.main import app
        from app.db import get_session
        app.dependency_overrides[get_session] = override_get_session
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()


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
