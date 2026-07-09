"""
User registration flow tests.

Coverage:
  - CAPTCHA challenge endpoint
  - Registration form page renders
  - New user registration (202)
  - Duplicate verified user rejected (409)
  - Unverified pending user replaced on re-registration
  - Email failure rolls back user row (503)
  - Verify page renders (with and without token)
  - Invalid / expired token rejection
  - Successful verification → redirect + API key email sent
  - Resend-key page renders
  - Resend for unregistered email (404)
  - Resend for verified user (200)
  - Verified API key accepted by protected endpoint
  - Unverified / unknown key rejected (401)
  - Display name loaded from DB (no stale cache)
"""

import time
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REG_PAYLOAD = {
    "email": "alice@example.com",
    "display_name": "Alice",
    "altcha_payload": "dummy",
}


def _register(client, email="alice@example.com", display_name="Alice"):
    return client.post(
        "/register",
        json={"email": email, "display_name": display_name, "altcha_payload": "dummy"},
    )


def _get_token(tmp_db, email):
    """Read verify_token straight from DB for the given email."""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def _verify(client, token):
    return client.post(
        "/verify",
        json={"token": token, "altcha_payload": "dummy"},
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# CAPTCHA challenge
# ---------------------------------------------------------------------------

def test_captcha_challenge(client):
    # Captcha not mocked here — just ensure endpoint returns required fields
    with patch("slacathon.main.create_challenge", return_value={
        "algorithm": "SHA-256", "challenge": "abc", "salt": "xyz", "signature": "sig"
    }):
        r = client.get("/captcha-challenge")
    assert r.status_code == 200
    data = r.json()
    assert {"algorithm", "challenge", "salt", "signature"} <= data.keys()


# ---------------------------------------------------------------------------
# Registration form page
# ---------------------------------------------------------------------------

def test_register_page_renders(client):
    r = client.get("/register")
    assert r.status_code == 200
    assert b"reg-form" in r.content


# ---------------------------------------------------------------------------
# New user registration
# ---------------------------------------------------------------------------

def test_register_new_user(client):
    r = _register(client, "bob@example.com")
    assert r.status_code == 202
    assert "email" in r.json()["detail"].lower()


def test_register_sends_verification_email(client):
    from slacathon.main import send_verification_email
    with patch("slacathon.main.send_verification_email", new_callable=AsyncMock) as mock_send:
        r = _register(client, "carol@example.com")
    assert r.status_code == 202
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert "carol@example.com" == call_args.args[0]
    assert "verify?token=" in call_args.args[1]


# ---------------------------------------------------------------------------
# Duplicate registration
# ---------------------------------------------------------------------------

def test_register_duplicate_verified_rejected(client, tmp_db):
    _register(client, "dave@example.com")
    row = _get_token(tmp_db, "dave@example.com")
    _verify(client, row["verify_token"])
    # Try to register again with same verified email
    r = _register(client, "dave@example.com")
    assert r.status_code == 409


def test_register_replaces_unverified_pending(client, tmp_db):
    _register(client, "eve@example.com")
    first = _get_token(tmp_db, "eve@example.com")
    # Re-register before verifying
    r = _register(client, "eve@example.com")
    assert r.status_code == 202
    second = _get_token(tmp_db, "eve@example.com")
    assert first["verify_token"] != second["verify_token"]


# ---------------------------------------------------------------------------
# Email failure atomicity
# ---------------------------------------------------------------------------

def test_register_rolls_back_on_email_failure(client, tmp_db):
    import sqlite3
    with patch("slacathon.main.send_verification_email", side_effect=Exception("SMTP down")):
        r = client.post(
            "/register",
            json={"email": "frank@example.com", "display_name": "Frank", "altcha_payload": "dummy"},
        )
    assert r.status_code == 503
    # Row must not persist
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT * FROM users WHERE email = ?", ("frank@example.com",)).fetchone()
    conn.close()
    assert row is None


# ---------------------------------------------------------------------------
# Verify page
# ---------------------------------------------------------------------------

def test_verify_page_with_token(client):
    r = client.get("/verify?token=sometoken")
    assert r.status_code == 200
    assert b"verify-form" in r.content


def test_verify_page_without_token_shows_error(client):
    r = client.get("/verify")
    assert r.status_code == 200
    assert b"ERROR" in r.content or b"error" in r.content.lower()


# ---------------------------------------------------------------------------
# Verify token — invalid / expired
# ---------------------------------------------------------------------------

def test_verify_invalid_token(client):
    r = _verify(client, "nonexistent-token-xyz")
    assert r.status_code == 404


def test_verify_expired_token(client, tmp_db):
    import sqlite3
    _register(client, "grace@example.com")
    # Force expiry in the past
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "UPDATE users SET expires_at = ? WHERE email = ?",
        (time.time() - 1, "grace@example.com"),
    )
    conn.commit()
    conn.close()
    row = _get_token(tmp_db, "grace@example.com")
    r = _verify(client, row["verify_token"])
    assert r.status_code == 410


# ---------------------------------------------------------------------------
# Successful verification
# ---------------------------------------------------------------------------

def test_verify_success_redirects(client, tmp_db):
    _register(client, "henry@example.com")
    row = _get_token(tmp_db, "henry@example.com")
    r = _verify(client, row["verify_token"])
    assert r.status_code == 303
    assert "registered" in r.headers["location"]


def test_verify_success_sends_api_key_email(client, tmp_db):
    _register(client, "iris@example.com")
    row = _get_token(tmp_db, "iris@example.com")
    with patch("slacathon.main.send_api_key_email", new_callable=AsyncMock) as mock_key:
        _verify(client, row["verify_token"])
    mock_key.assert_awaited_once()
    assert mock_key.call_args.args[0] == "iris@example.com"


def test_verify_marks_user_verified(client, tmp_db):
    import sqlite3
    _register(client, "jack@example.com")
    row = _get_token(tmp_db, "jack@example.com")
    _verify(client, row["verify_token"])
    conn = sqlite3.connect(tmp_db)
    updated = conn.execute(
        "SELECT verified, verify_token FROM users WHERE email = ?", ("jack@example.com",)
    ).fetchone()
    conn.close()
    assert updated[0] == 1
    assert updated[1] is None


# ---------------------------------------------------------------------------
# Resend key
# ---------------------------------------------------------------------------

def test_resend_key_page_renders(client):
    r = client.get("/resend-key")
    assert r.status_code == 200
    assert b"resend-form" in r.content


def test_resend_key_unknown_email(client):
    r = client.post(
        "/resend-key",
        json={"email": "nobody@example.com", "altcha_payload": "dummy"},
    )
    assert r.status_code == 404


def test_resend_key_verified_user(client, tmp_db):
    _register(client, "kate@example.com")
    row = _get_token(tmp_db, "kate@example.com")
    _verify(client, row["verify_token"])
    with patch("slacathon.main.send_api_key_email", new_callable=AsyncMock) as mock_key:
        r = client.post(
            "/resend-key",
            json={"email": "kate@example.com", "altcha_payload": "dummy"},
        )
    assert r.status_code == 200
    mock_key.assert_awaited_once()


def test_resend_key_unverified_user_rejected(client, tmp_db):
    _register(client, "liam@example.com")
    # Not verified — resend should 404
    r = client.post(
        "/resend-key",
        json={"email": "liam@example.com", "altcha_payload": "dummy"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Registered page
# ---------------------------------------------------------------------------

def test_registered_page_renders(client):
    r = client.get("/registered")
    assert r.status_code == 200
    assert b"VERIFIED" in r.content or b"verified" in r.content.lower()


# ---------------------------------------------------------------------------
# API key authentication (no cache)
# ---------------------------------------------------------------------------

def test_verified_api_key_accepted(client, tmp_db):
    import sqlite3
    _register(client, "mike@example.com")
    row = _get_token(tmp_db, "mike@example.com")
    _verify(client, row["verify_token"])
    # Fetch the issued API key from DB
    conn = sqlite3.connect(tmp_db)
    updated = conn.execute(
        "SELECT api_key FROM users WHERE email = ?", ("mike@example.com",)
    ).fetchone()
    conn.close()
    api_key = updated[0]
    r = client.get("/history", headers={"X-API-Key": api_key})
    assert r.status_code == 200


def test_unknown_api_key_rejected(client):
    r = client.get("/history", headers={"X-API-Key": "completely-fake-key-xyz"})
    assert r.status_code == 401


def test_unverified_user_key_rejected(client, tmp_db):
    import sqlite3
    _register(client, "nina@example.com")
    # Row exists but verified=0; api_key is the row_id placeholder (not yet a real key)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT api_key FROM users WHERE email = ?", ("nina@example.com",)
    ).fetchone()
    conn.close()
    r = client.get("/history", headers={"X-API-Key": row[0]})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Display name — live DB read
# ---------------------------------------------------------------------------

def test_get_display_name_from_db(tmp_db):
    """get_display_name must reflect DB state without any in-process cache."""
    import sqlite3
    from slacathon.middleware import get_display_name

    # Insert a user directly
    api_key = "test-display-key-999"
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "INSERT OR REPLACE INTO users (api_key, display_name, verified) VALUES (?, ?, 1)",
        (api_key, "DirectInsert"),
    )
    conn.commit()
    conn.close()

    # Should find it immediately (no restart, no cache warm-up)
    assert get_display_name(api_key) == "DirectInsert"


def test_get_display_name_unknown_key():
    from slacathon.middleware import get_display_name
    assert get_display_name("no-such-key") == "Anonymous"
