# Phase 05 — Registration Router

## Scope
Create `app/routers/registration.py` with all 4 endpoints.
`app/main.py` not yet modified — router exists but is not mounted.
No existing functionality changed.

## Prereq
Phases 01–04 complete (settings, DB, captcha, email service, templates all exist).

## Files Created
| File | Purpose |
|---|---|
| `app/routers/registration.py` | `GET /register`, `POST /register`, `GET /verify`, `POST /verify` |

---

## `app/routers/registration.py`

```python
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from app.db import get_session
from app.models.user import User
from app.settings import settings
from app.captcha import verify_captcha
from app.email_service import send_verification_email, send_api_key_email

logger = logging.getLogger(__name__)
router = APIRouter()

_templates = Jinja2Templates(directory="app/page_templates")


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str
    h_captcha_response: str


class VerifyRequest(BaseModel):
    token: str
    h_captcha_response: str


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return _templates.TemplateResponse(
        "register.html.j2",
        {"request": request, "site_key": settings.hcaptcha_site_key, "root_path": settings.root_path},
    )


@router.post("/register", status_code=202)
async def register(body: RegisterRequest, session: Session = Depends(get_session)):
    await verify_captcha(body.h_captcha_response)

    existing: Optional[User] = session.exec(select(User).where(User.email == body.email)).first()

    if existing:
        if existing.verified:
            raise HTTPException(status_code=409, detail="Email already registered")
        # Unverified — delete and re-register
        session.delete(existing)
        session.commit()

    api_key = secrets.token_urlsafe(32)
    verify_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=settings.verify_timeout_hours)

    user = User(
        email=body.email,
        display_name=body.display_name.strip()[:40],
        api_key=api_key,
        verified=False,
        verify_token=verify_token,
        expires_at=expires_at,
    )
    session.add(user)
    session.commit()

    verify_url = f"{settings.public_url}{settings.root_path}/verify?token={verify_token}"
    await send_verification_email(body.email, verify_url, settings.verify_timeout_hours)

    logger.info(f"Registration initiated for {body.email}")
    return {"detail": "Check your email — verification link sent"}


@router.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request, token: str = ""):
    if not token:
        return _templates.TemplateResponse(
            "verify.html.j2",
            {"request": request, "token": "", "site_key": settings.hcaptcha_site_key,
             "root_path": settings.root_path, "error": "Missing verification token"},
        )
    return _templates.TemplateResponse(
        "verify.html.j2",
        {"request": request, "token": token, "site_key": settings.hcaptcha_site_key,
         "root_path": settings.root_path, "error": None},
    )


@router.post("/verify")
async def verify_email(body: VerifyRequest, session: Session = Depends(get_session)):
    await verify_captcha(body.h_captcha_response)

    user: Optional[User] = session.exec(
        select(User).where(User.verify_token == body.token)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Invalid or expired link")

    if user.expires_at and user.expires_at < datetime.utcnow():
        session.delete(user)
        session.commit()
        raise HTTPException(status_code=410, detail="Link expired — please register again")

    user.verified = True
    user.expires_at = None
    user.verify_token = "__used__"
    session.add(user)
    session.commit()

    await send_api_key_email(user.email, user.api_key)
    logger.info(f"Email verified for {user.email}")

    return RedirectResponse(url=f"{settings.root_path}/?registered=1", status_code=303)
```

---

## Acceptance Criteria
- `from app.routers.registration import router` imports without error
- Module-level structure check: 4 routes registered (`/register` GET+POST, `/verify` GET+POST)
- No import of `app.main` or circular deps

---

## Test Suite: `tests/test_phase05_registration_router.py`

```python
"""Phase 05 — registration router endpoint tests (no real SMTP, no real captcha)."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlmodel import Session, SQLModel, create_engine
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
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
    with patch("app.routers.registration.verify_captcha", new_callable=AsyncMock) as _cap, \
         patch("app.routers.registration.send_verification_email", new_callable=AsyncMock) as _vmail, \
         patch("app.routers.registration.send_api_key_email", new_callable=AsyncMock) as _kmail:
        yield _cap, _vmail, _kmail


def test_get_register_page(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    assert "SLACATHON" in resp.text


def test_post_register_new_user(client):
    resp = client.post("/register", json={
        "email": "newuser@test.com",
        "display_name": "Tester",
        "h_captcha_response": "tok",
    })
    assert resp.status_code == 202
    assert "email" in resp.json()["detail"].lower()


def test_post_register_duplicate_verified(client, mem_engine):
    from app.models.user import User
    from sqlmodel import Session
    with Session(mem_engine) as s:
        s.add(User(email="verified@test.com", display_name="V", api_key="vkey1",
                   verified=True, verify_token="used"))
        s.commit()
    resp = client.post("/register", json={
        "email": "verified@test.com",
        "display_name": "V2",
        "h_captcha_response": "tok",
    })
    assert resp.status_code == 409


def test_post_register_replaces_unverified(client, mem_engine):
    from app.models.user import User
    from sqlmodel import Session, select
    with Session(mem_engine) as s:
        s.add(User(email="unverified@test.com", display_name="U", api_key="ukey1",
                   verified=False, verify_token="old-tok"))
        s.commit()
    resp = client.post("/register", json={
        "email": "unverified@test.com",
        "display_name": "U2",
        "h_captcha_response": "tok",
    })
    assert resp.status_code == 202
    with Session(mem_engine) as s:
        users = s.exec(select(User).where(User.email == "unverified@test.com")).all()
        assert len(users) == 1
        assert users[0].display_name == "U2"


def test_get_verify_page_no_token(client):
    resp = client.get("/verify")
    assert resp.status_code == 200
    assert "Missing" in resp.text or "ERROR" in resp.text


def test_get_verify_page_with_token(client):
    resp = client.get("/verify?token=sometoken")
    assert resp.status_code == 200
    assert "sometoken" in resp.text


def test_post_verify_invalid_token(client):
    resp = client.post("/verify", json={"token": "badtoken", "h_captcha_response": "tok"})
    assert resp.status_code == 404


def test_post_verify_expired_token(client, mem_engine):
    from app.models.user import User
    from sqlmodel import Session
    from datetime import datetime, timedelta
    with Session(mem_engine) as s:
        s.add(User(email="expired@test.com", display_name="E", api_key="ekey1",
                   verified=False, verify_token="expired-tok",
                   expires_at=datetime.utcnow() - timedelta(hours=1)))
        s.commit()
    resp = client.post("/verify", json={"token": "expired-tok", "h_captcha_response": "tok"})
    assert resp.status_code == 410


def test_post_verify_success(client, mem_engine):
    from app.models.user import User
    from sqlmodel import Session, select
    from datetime import datetime, timedelta
    with Session(mem_engine) as s:
        s.add(User(email="ok@test.com", display_name="OK", api_key="okkey1",
                   verified=False, verify_token="valid-tok",
                   expires_at=datetime.utcnow() + timedelta(hours=24)))
        s.commit()
    resp = client.post("/verify", json={"token": "valid-tok", "h_captcha_response": "tok"},
                       follow_redirects=False)
    assert resp.status_code == 303
    with Session(mem_engine) as s:
        user = s.exec(select(User).where(User.email == "ok@test.com")).first()
        assert user.verified is True
        assert user.expires_at is None
```
