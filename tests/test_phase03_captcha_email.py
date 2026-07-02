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
    from altcha.v1 import solve_challenge

    ch = create_challenge()
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
        combined = "".join(p.get_payload(decode=True).decode() for p in payload) if isinstance(payload, list) else str(payload)
        assert "my-api-key-xyz" in combined


def test_templates_render():
    from jinja2 import Environment, FileSystemLoader
    from pathlib import Path
    env = Environment(loader=FileSystemLoader(str(Path("app/email_templates"))))
    body = env.get_template("verify_email.html.j2").render(verify_url="http://x.y/v", timeout_hours=24)
    assert "http://x.y/v" in body
    body2 = env.get_template("api_key_delivery.html.j2").render(api_key="key-abc")
    assert "key-abc" in body2
