import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Temporary SQLite DB path for the whole test session."""
    d = tmp_path_factory.mktemp("data")
    return str(d / "test_slacathon.db")


@pytest.fixture(scope="session")
def tmp_leaderboard(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    return str(d / "test_leaderboard.json")


@pytest.fixture(scope="session")
def app(tmp_db, tmp_leaderboard):
    """FastAPI app wired to temp DB and leaderboard."""
    os.environ["SLACATHON_DB_FILE"] = tmp_db
    os.environ["SLACATHON_LEADERBOARD_FILE"] = tmp_leaderboard
    os.environ["SLACATHON_PUBLIC_URL"] = "http://testserver"
    os.environ["SLACATHON_SMTP_HOST"] = "localhost"
    os.environ["SLACATHON_SMTP_PORT"] = "1025"
    os.environ["SLACATHON_ALTCHA_HMAC_KEY"] = "test-hmac-key"
    os.environ["SLACATHON_API_KEYS"] = ""

    # Import after env is set so settings picks up overrides
    from slacathon import db
    db.DB_PATH = tmp_db
    db.init_db()

    from slacathon.main import app as _app
    return _app


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(autouse=True)
def patch_externals():
    """Suppress real CAPTCHA verification and email sending in every test."""
    with (
        patch("slacathon.main.verify_captcha"),
        patch("slacathon.main.send_verification_email", new_callable=AsyncMock),
        patch("slacathon.main.send_api_key_email", new_callable=AsyncMock),
    ):
        yield
