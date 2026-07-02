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
from app.captcha import create_challenge, verify_captcha
from app.email_service import send_verification_email, send_api_key_email

logger = logging.getLogger(__name__)
router = APIRouter()

_templates = Jinja2Templates(directory="app/page_templates")


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str
    altcha_payload: str


class VerifyRequest(BaseModel):
    token: str
    altcha_payload: str


@router.get("/captcha-challenge")
async def captcha_challenge():
    return create_challenge()


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return _templates.TemplateResponse(
        request, "register.html.j2",
        {"root_path": settings.root_path},
    )


@router.post("/register", status_code=202)
async def register(body: RegisterRequest, session: Session = Depends(get_session)):
    verify_captcha(body.altcha_payload)

    existing: Optional[User] = session.exec(select(User).where(User.email == body.email)).first()

    if existing:
        if existing.verified:
            raise HTTPException(status_code=409, detail="Email already registered")
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
            request, "verify.html.j2",
            {"token": "", "root_path": settings.root_path, "error": "Missing verification token"},
        )
    return _templates.TemplateResponse(
        request, "verify.html.j2",
        {"token": token, "root_path": settings.root_path, "error": None},
    )


@router.post("/verify")
async def verify_email(body: VerifyRequest, session: Session = Depends(get_session)):
    verify_captcha(body.altcha_payload)

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
