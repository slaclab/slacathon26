# Phase 03 — Captcha Helper & Email Service

## Scope
Create `app/captcha.py` and `app/email_service.py` plus Jinja2 email templates.
No routes. No DB writes. No existing code modified.

## Prereq
Phase 01 (settings fields exist), Phase 02 (User model — email service imports it for type hints).

## Files Created
| File | Purpose |
|---|---|
| `app/captcha.py` | `verify_captcha(token)` async helper |
| `app/email_service.py` | `send_verification_email()`, `send_api_key_email()` |
| `app/email_templates/verify_email.html.j2` | Verification email body |
| `app/email_templates/api_key_delivery.html.j2` | API key delivery email body |

---

## `app/captcha.py`

```python
import httpx
from fastapi import HTTPException
from app.settings import settings


async def verify_captcha(token: str):
    if not token:
        raise HTTPException(status_code=400, detail="CAPTCHA token missing")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            settings.hcaptcha_verify_url,
            data={"secret": settings.hcaptcha_secret_key, "response": token},
        )
    result = resp.json()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed")
```

---

## `app/email_service.py`

```python
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.settings import settings

logger = logging.getLogger(__name__)

_env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "email_templates")))


async def _send(to: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
    )
    logger.info(f"Email sent to {to}: {subject}")


async def send_verification_email(to: str, verify_url: str, timeout_hours: int):
    tmpl = _env.get_template("verify_email.html.j2")
    body = tmpl.render(verify_url=verify_url, timeout_hours=timeout_hours)
    await _send(to, "Verify your SLACATHON'26 account", body)


async def send_api_key_email(to: str, api_key: str):
    tmpl = _env.get_template("api_key_delivery.html.j2")
    body = tmpl.render(api_key=api_key)
    await _send(to, "Your SLACATHON'26 API Key", body)
```

---

## `app/email_templates/verify_email.html.j2`

```html
<!DOCTYPE html>
<html>
<body style="font-family:monospace;background:#000;color:#00ff00;padding:32px;">
<pre>
Subject: Verify your SLACATHON'26 account

Hello,

Click the link below to verify your email address.
This link expires in {{ timeout_hours }} hours.

{{ verify_url }}

If you did not request this, ignore this email.
</pre>
</body>
</html>
```

---

## `app/email_templates/api_key_delivery.html.j2`

```html
<!DOCTYPE html>
<html>
<body style="font-family:monospace;background:#000;color:#00ff00;padding:32px;">
<pre>
Subject: Your SLACATHON'26 API Key

Hello,

Your email has been verified. Here is your API key:

  {{ api_key }}

Use it as:
  Authorization: Bearer {{ api_key }}
  — or —
  X-API-Key: {{ api_key }}

Do not share this key. If lost, re-register with the same email.
</pre>
</body>
</html>
```

---

## Acceptance Criteria
- `from app.captcha import verify_captcha` imports without error
- `from app.email_service import send_verification_email` imports without error
- Both email templates render with Jinja2 without error
- `verify_captcha("")` raises `HTTPException(400)`

---

## Test Suite: `tests/test_phase03_captcha_email.py`

```python
"""Phase 03 — captcha helper and email service unit tests."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException


# --- captcha ---

@pytest.mark.asyncio
async def test_verify_captcha_empty_token():
    from app.captcha import verify_captcha
    with pytest.raises(HTTPException) as exc:
        await verify_captcha("")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_captcha_success():
    from app.captcha import verify_captcha
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        await verify_captcha("valid-token")  # no exception


@pytest.mark.asyncio
async def test_verify_captcha_failure():
    from app.captcha import verify_captcha
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": False}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(HTTPException) as exc:
            await verify_captcha("bad-token")
        assert exc.value.status_code == 400


# --- email service ---

@pytest.mark.asyncio
async def test_send_verification_email():
    from app.email_service import send_verification_email
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_verification_email("u@test.com", "http://verify.link/tok", 24)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        msg = args[0]
        assert "u@test.com" in msg["To"]


@pytest.mark.asyncio
async def test_send_api_key_email():
    from app.email_service import send_api_key_email
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_api_key_email("u@test.com", "my-api-key-xyz")
        mock_send.assert_called_once()
        # verify key appears in rendered body
        args, _ = mock_send.call_args
        msg = args[0]
        payload = msg.get_payload()
        combined = "".join(p.get_payload() for p in payload) if isinstance(payload, list) else str(payload)
        assert "my-api-key-xyz" in combined


def test_templates_render():
    from jinja2 import Environment, FileSystemLoader
    from pathlib import Path
    env = Environment(loader=FileSystemLoader(str(Path("app/email_templates"))))
    body = env.get_template("verify_email.html.j2").render(verify_url="http://x.y/v", timeout_hours=24)
    assert "http://x.y/v" in body
    body2 = env.get_template("api_key_delivery.html.j2").render(api_key="key-abc")
    assert "key-abc" in body2
```
