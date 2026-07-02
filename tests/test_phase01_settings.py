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
    assert isinstance(settings.root_path, str)


def test_env_override(monkeypatch):
    """New fields respect SLACATHON_ prefix override."""
    monkeypatch.setenv("SLACATHON_SMTP_PORT", "2525")
    from importlib import reload
    import app.settings as s_mod
    reload(s_mod)
    assert s_mod.settings.smtp_port == 2525
    # restore
    reload(s_mod)
