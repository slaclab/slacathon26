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
