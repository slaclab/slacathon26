"""Phase 07 — DB-backed API key auth and display name resolution."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from unittest.mock import patch


@pytest.fixture(scope="module")
def mem_engine():
    from app.models.user import User  # noqa
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
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


def test_leaderboard_entry_db_model(mem_engine):
    import json
    from app.models.leaderboard_entry import LeaderboardEntry
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(mem_engine)
    entry = LeaderboardEntry(
        user_id="uid1", display_name="Alice",
        input_json=json.dumps({"q1": 0.1}),
        score=0.5, solved=False, timestamp=1000.0,
    )
    with Session(mem_engine) as s:
        s.add(entry)
        s.commit()
        s.refresh(entry)
    assert entry.display_name == "Alice"
    assert entry.score == 0.5


def test_add_to_leaderboard_with_session(mem_engine):
    from app.core.middleware import add_to_leaderboard, get_leaderboard
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(mem_engine)
    with Session(mem_engine) as s:
        rank = add_to_leaderboard("good_key", {"q1": 0.2}, 0.42, False, s)
        board = get_leaderboard(s)
    assert any(e["user"] == "Alice" for e in board)
