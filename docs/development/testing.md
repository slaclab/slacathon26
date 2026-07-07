# Testing

## Run All Tests

```bash
python -m pytest
```

## Run a Specific Phase

```bash
python -m pytest tests/test_phase05_registration_router.py
```

## Test Structure

Tests are organized into phases mirroring the implementation phases:

| File | Phase | Coverage |
|------|-------|----------|
| `test_phase01_settings.py` | Settings | Field defaults, env overrides, model_fields inspection |
| `test_phase02_db.py` | Database | User CRUD, uniqueness, dev seeding |
| `test_phase03_captcha_email.py` | CAPTCHA + Email | Challenge creation, verification, email dispatch |
| `test_phase04_templates.py` | Templates | Jinja2 template rendering |
| `test_phase05_registration_router.py` | Registration | Full register/verify/resend flow, error cases, atomic rollback |
| `test_phase06_main_wiring.py` | App wiring | Route mounting, task loading, health check |
| `test_phase07_middleware_db_auth.py` | Auth + Leaderboard | Key validation, display name resolution, leaderboard DB ops |
| `test_phase08_compose.py` | Compose config | devcontainer.json, docker-compose.yml, .env.example structure |

## Test Fixtures

Most tests use in-memory SQLite with `StaticPool` to keep all connections on the same database:

```python
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(engine)
```

FastAPI endpoints are tested via `TestClient` with `app.dependency_overrides[get_session]` pointing at the test engine.

## Async Tests

`pytest.ini` sets `asyncio_mode = auto`, so async test functions work without decoration:

```python
async def test_something():
    ...
```

## Configuration Tests

`test_phase01_settings.py` inspects `model_fields` directly to verify defaults without interference from environment variables:

```python
from app.settings import Settings
fields = Settings.model_fields
assert fields["smtp_host"].default == "localhost"
```
