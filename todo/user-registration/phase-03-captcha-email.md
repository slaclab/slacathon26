# Phase 03 — Captcha Helper & Email Service

## Scope
Create `app/captcha.py` and `app/email_service.py` plus Jinja2 email templates.
No routes. No DB writes. No existing code modified.

**Captcha: Altcha** — self-hosted proof-of-work. No external server. No API keys beyond
the `altcha_hmac_key` in settings. Client solves a SHA-256 challenge in-browser; server
verifies the solution locally using the `altcha` Python package.

## Prereq
Phase 01 (settings fields exist), Phase 02 (User model — email service imports it for type hints).

## Files Created
| File | Purpose |
|---|---|
| `app/captcha.py` | `create_challenge()` + `verify_captcha(payload)` using Altcha |
| `app/email_service.py` | `send_verification_email()`, `send_api_key_email()` |
| `app/email_templates/verify_email.html.j2` | Verification email body |
| `app/email_templates/api_key_delivery.html.j2` | API key delivery email body |

---

## `app/captcha.py`

Altcha flow:
1. `GET /captcha-challenge` → server calls `create_challenge()` → returns JSON challenge
2. Browser widget solves it (SHA-256 proof-of-work, runs in JS)
3. Widget encodes solution as base64 JSON → `altcha_payload` field in form submission
4. Server calls `verify_captcha(altcha_payload)` → validates locally, no HTTP

```python
import base64
import json
import logging
from fastapi import HTTPException
from altcha import create_challenge as _create, verify_solution, ChallengeOptions
from app.settings import settings

logger = logging.getLogger(__name__)


def create_challenge() -> dict:
    """Generate a new Altcha proof-of-work challenge. Call from GET /captcha-challenge."""
    challenge = _create(ChallengeOptions(hmac_key=settings.altcha_hmac_key))
    return {
        "algorithm": challenge.algorithm,
        "challenge": challenge.challenge,
        "salt": challenge.salt,
        "signature": challenge.signature,
    }


def verify_captcha(payload: str):
    """
    Verify Altcha widget payload (base64-encoded JSON solution from browser).
    Raises HTTPException(400) on missing or invalid payload.
    """
    if not payload:
        raise HTTPException(status_code=400, detail="CAPTCHA solution missing")
    try:
        decoded = base64.b64decode(payload).decode()
        solution = json.loads(decoded)
    except Exception:
        raise HTTPException(status_code=400, detail="CAPTCHA payload malformed")

    ok = verify_solution(solution, settings.altcha_hmac_key)
    if not ok:
        logger.warning("Altcha verification failed")
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
- `from app.captcha import create_challenge, verify_captcha` imports without error
- `create_challenge()` returns dict with keys: `algorithm`, `challenge`, `salt`, `signature`
- `verify_captcha("")` raises `HTTPException(400)`
- `verify_captcha("not-base64!!")` raises `HTTPException(400)`
- `from app.email_service import send_verification_email` imports without error
- Both email templates render with Jinja2 without error

---

## Test Suite: `tests/test_phase03_captcha_email.py`

```python
"""Phase 03 — Altcha captcha helper and email service unit tests."""
import pytest
import base64
import json
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException


# --- captcha ---

def test_create_challenge_returns_required_fields():
    from app.captcha import create_challenge
    ch = create_challenge()
    for key in ("algorithm", "challenge", "salt", "signature"):
        assert key in ch, f"Missing field: {key}"


def test_verify_captcha_empty_raises():
    from app.captcha import verify_captcha
    with pytest.raises(HTTPException) as exc:
        verify_captcha("")
    assert exc.value.status_code == 400


def test_verify_captcha_malformed_raises():
    from app.captcha import verify_captcha
    with pytest.raises(HTTPException) as exc:
        verify_captcha("not-valid-base64!!!")
    assert exc.value.status_code == 400


def test_verify_captcha_wrong_solution_raises():
    from app.captcha import verify_captcha
    # Valid base64 JSON but wrong solution
    fake = base64.b64encode(json.dumps({"algorithm": "SHA-256", "challenge": "x",
                                        "number": 0, "salt": "s", "signature": "bad"}).encode()).decode()
    with pytest.raises(HTTPException) as exc:
        verify_captcha(fake)
    assert exc.value.status_code == 400


def test_verify_captcha_valid_roundtrip():
    """Create a challenge then produce a valid solution and verify it passes."""
    from app.captcha import create_challenge, verify_captcha
    from altcha import solve_challenge

    ch = create_challenge()
    # altcha.solve_challenge brute-forces the PoW — fast at default complexity
    solution = solve_challenge(ch["challenge"], ch["salt"], ch["algorithm"], max_number=1_000_000)
    assert solution is not None, "solve_challenge returned None — challenge unsolvable at max_number"

    payload = base64.b64encode(json.dumps({
        "algorithm": ch["algorithm"],
        "challenge": ch["challenge"],
        "number": solution.number,
        "salt": ch["salt"],
        "signature": ch["signature"],
    }).encode()).decode()

    verify_captcha(payload)  # must not raise


# --- email service ---

@pytest.mark.asyncio
async def test_send_verification_email():
    from app.email_service import send_verification_email
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_verification_email("u@test.com", "http://verify.link/tok", 24)
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        msg = args[0]
        assert "u@test.com" in msg["To"]


@pytest.mark.asyncio
async def test_send_api_key_email():
    from app.email_service import send_api_key_email
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_api_key_email("u@test.com", "my-api-key-xyz")
        mock_send.assert_called_once()
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
