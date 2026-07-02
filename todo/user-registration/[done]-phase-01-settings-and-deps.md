# Phase 01 — Settings & Dependencies

## Scope
Add new config fields to `app/settings.py` and update `requirements.txt`.
No behavior changes. No DB. No routes. Zero breakage risk.

## Files Changed
| File | Change |
|---|---|
| `app/settings.py` | Add 7 new optional fields |
| `requirements.txt` | Add 5 new packages |

## Settings additions (`app/settings.py`)

Add to `Settings` class:

```python
# SMTP
smtp_host: str = Field(default="localhost")
smtp_port: int = Field(default=1025)
smtp_from: str = Field(default="noreply@slacathon26.local")

# Public URL (base for verify links in emails)
public_url: str = Field(default="http://localhost:8000")

# Registration
verify_timeout_hours: int = Field(default=24)
cleanup_interval_minutes: int = Field(default=10)

# Altcha (self-hosted proof-of-work CAPTCHA — no external service)
altcha_hmac_key: str = Field(default="dev-hmac-key-change-in-prod")
```

`altcha_hmac_key` is the server-side secret used to sign and verify Altcha challenges.
**Change in production** — any non-empty string works, longer = more secure.

## requirements.txt additions

```
sqlmodel
aiosmtplib
jinja2
email-validator
altcha
```

Note: `jinja2` may already be pulled by FastAPI; explicit pin is fine.
`httpx` is NOT needed — Altcha verification is fully local (no external HTTP calls).

## Acceptance Criteria
- `python -c "from app.settings import settings; print(settings.smtp_host)"` prints `localhost`
- All 7 new fields accessible without error
- `pip install -r requirements.txt` succeeds

---

## Test Suite: `tests/test_phase01_settings.py`

```python
"""Phase 01 — settings fields and deps smoke test."""
import pytest
from app.settings import settings


def test_smtp_defaults():
    assert settings.smtp_host == "localhost"
    assert settings.smtp_port == 1025
    assert settings.smtp_from == "noreply@slacathon26.local"


def test_public_url_default():
    assert settings.public_url.startswith("http")


def test_registration_defaults():
    assert settings.verify_timeout_hours > 0
    assert settings.cleanup_interval_minutes > 0


def test_altcha_defaults():
    assert settings.altcha_hmac_key != ""


def test_existing_settings_unchanged():
    """Regression: existing fields must still work."""
    assert hasattr(settings, "api_keys")
    assert hasattr(settings, "leaderboard_file")
    assert hasattr(settings, "root_path")
    assert settings.root_path == "/slacathon26"


def test_env_override(monkeypatch):
    """New fields respect SLACATHON_ prefix override."""
    monkeypatch.setenv("SLACATHON_SMTP_PORT", "2525")
    from importlib import reload
    import app.settings as s_mod
    reload(s_mod)
    assert s_mod.settings.smtp_port == 2525
    # restore
    reload(s_mod)
```
