# Testing

## Test Stack

- **pytest** ≥ 8.0
- **pytest-asyncio** (async test support)
- **httpx** (FastAPI `TestClient` backend)

Install dev extras:

```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
# All tests
pytest

# With verbose output
pytest -v

# Single file
pytest tests/test_flat_beam.py

# Single test
pytest tests/test_registration.py::test_register_and_verify
```

## Test Files

| File | What it covers |
|---|---|
| `tests/test_flat_beam.py` | Import + basic smoke test for `flat_beam` task |
| `tests/test_leaderboard.py` | Leaderboard add/dedup/sort logic |
| `tests/test_quota.py` | Quota enforcement, atomic charge, limit reached |
| `tests/test_registration.py` | Full registration + verification flow via `TestClient` |

## Fixtures (`tests/conftest.py`)

| Fixture | Scope | Purpose |
|---|---|---|
| `tmp_db` | session | Temp SQLite path (`/tmp/*/test_slacathon.db`) |
| `tmp_leaderboard` | session | Temp leaderboard JSON path |
| `app` | session | FastAPI app wired to temp files; sets env vars before import |
| `client` | session | `TestClient(app)` |
| `patch_externals` | autouse | Suppresses real CAPTCHA verification and SMTP calls in all tests |

`patch_externals` patches:
- `slacathon.main.verify_captcha` → no-op
- `slacathon.main.send_verification_email` → `AsyncMock`
- `slacathon.main.send_api_key_email` → `AsyncMock`

## Configuration

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
```

`asyncio_mode = "auto"` means all async test functions run automatically without `@pytest.mark.asyncio`.

## Notes

- `fel` and `cuinj` tasks are not covered by automated tests because they call an external SLAC model service. Test them manually against a running instance with network access to the SLAC ARD service.
- The `flat_beam` task is fully local and safe to test in CI.
