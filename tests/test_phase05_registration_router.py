"""Phase 05 — registration router endpoint tests (Altcha, no real SMTP)."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch


@pytest.fixture(scope="module")
def app_with_router():
    from app.routers.registration import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(scope="module")
def mem_engine():
    from app.models.user import User  # noqa
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="module")
def client(app_with_router, mem_engine):
    from app.db import get_session
    def override_session():
        with Session(mem_engine) as s:
            yield s
    app_with_router.dependency_overrides[get_session] = override_session
    return TestClient(app_with_router, raise_server_exceptions=True)


# Patch captcha to always pass and email to no-op
@pytest.fixture(autouse=True)
def patch_externals():
    with patch("app.routers.registration.verify_captcha") as _cap, \
         patch("app.routers.registration.send_verification_email", new_callable=AsyncMock) as _vmail, \
         patch("app.routers.registration.send_api_key_email", new_callable=AsyncMock) as _kmail:
        yield _cap, _vmail, _kmail


def test_captcha_challenge_endpoint(client):
    resp = client.get("/captcha-challenge")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("algorithm", "challenge", "salt", "signature"):
        assert key in data


def test_get_register_page(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    assert "SLACATHON" in resp.text
    assert "altcha-widget" in resp.text


def test_post_register_new_user(client):
    resp = client.post("/register", json={
        "email": "newuser@test.com",
        "display_name": "Tester",
        "altcha_payload": "fake-but-mocked",
    })
    assert resp.status_code == 202
    assert "email" in resp.json()["detail"].lower()


def test_post_register_duplicate_verified(client, mem_engine):
    from app.models.user import User
    with Session(mem_engine) as s:
        s.add(User(email="verified@test.com", display_name="V", api_key="vkey1",
                   verified=True, verify_token="used"))
        s.commit()
    resp = client.post("/register", json={
        "email": "verified@test.com",
        "display_name": "V2",
        "altcha_payload": "fake",
    })
    assert resp.status_code == 409


def test_post_register_replaces_unverified(client, mem_engine):
    from app.models.user import User
    from sqlmodel import select
    with Session(mem_engine) as s:
        s.add(User(email="unverified@test.com", display_name="U", api_key="ukey1",
                   verified=False, verify_token="old-tok"))
        s.commit()
    resp = client.post("/register", json={
        "email": "unverified@test.com",
        "display_name": "U2",
        "altcha_payload": "fake",
    })
    assert resp.status_code == 202
    with Session(mem_engine) as s:
        users = s.exec(select(User).where(User.email == "unverified@test.com")).all()
        assert len(users) == 1
        assert users[0].display_name == "U2"


def test_post_register_email_failure_returns_503_and_rolls_back(client, mem_engine):
    from app.models.user import User
    from sqlmodel import select

    with patch("app.routers.registration.send_verification_email", new_callable=AsyncMock) as mocked_send:
        mocked_send.side_effect = RuntimeError("smtp down")
        resp = client.post("/register", json={
            "email": "mailfail@test.com",
            "display_name": "MF",
            "altcha_payload": "fake",
        })

    assert resp.status_code == 503
    assert "email service unavailable" in resp.json()["detail"].lower()

    with Session(mem_engine) as s:
        user = s.exec(select(User).where(User.email == "mailfail@test.com")).first()
        assert user is None


def test_get_verify_page_no_token(client):
    resp = client.get("/verify")
    assert resp.status_code == 200
    assert "Missing" in resp.text or "ERROR" in resp.text


def test_get_verify_page_with_token(client):
    resp = client.get("/verify?token=sometoken")
    assert resp.status_code == 200
    assert "sometoken" in resp.text
    assert "altcha-widget" in resp.text


def test_post_verify_invalid_token(client):
    resp = client.post("/verify", json={"token": "badtoken", "altcha_payload": "fake"})
    assert resp.status_code == 404


def test_post_verify_expired_token(client, mem_engine):
    from app.models.user import User
    from datetime import datetime, timedelta
    with Session(mem_engine) as s:
        s.add(User(email="expired@test.com", display_name="E", api_key="ekey1",
                   verified=False, verify_token="expired-tok",
                   expires_at=datetime.utcnow() - timedelta(hours=1)))
        s.commit()
    resp = client.post("/verify", json={"token": "expired-tok", "altcha_payload": "fake"})
    assert resp.status_code == 410


def test_post_verify_success(client, mem_engine):
    from app.models.user import User
    from sqlmodel import select
    from datetime import datetime, timedelta
    with Session(mem_engine) as s:
        s.add(User(email="ok@test.com", display_name="OK", api_key="okkey1",
                   verified=False, verify_token="valid-tok",
                   expires_at=datetime.utcnow() + timedelta(hours=24)))
        s.commit()
    resp = client.post("/verify", json={"token": "valid-tok", "altcha_payload": "fake"},
                       follow_redirects=False)
    assert resp.status_code == 303
    with Session(mem_engine) as s:
        user = s.exec(select(User).where(User.email == "ok@test.com")).first()
        assert user.verified is True
        assert user.expires_at is None
