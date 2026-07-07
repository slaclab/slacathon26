# Components

## `app/main.py`

FastAPI application entry point. Responsibilities:

- Mount static files at `/static`
- Register routers: `jobs`, `leaderboard`, `registration`
- Load active task at startup (validates protocol, sets quota limit)
- Run `create_db_and_tables()` on startup
- Start `_cleanup_loop` background coroutine (removes expired unverified users)

## `app/settings.py`

Pydantic `BaseSettings` subclass. All fields read from `SLACATHON_*` environment variables or `.env` file. Post-processes `api_keys` string into a list in-place after instantiation.

## `app/db.py`

SQLite engine at `sqlite:///./data/slacathon26.db`. Provides `get_session()` generator for FastAPI dependency injection. Seeds three dev users on first startup (`key_123`, `key_456`, `key_789`).

## `app/core/middleware.py`

Stateless auth and leaderboard helpers. No module-level globals after the DB migration.

| Function | Used by |
|----------|---------|
| `verify_api_key(header, session)` | All protected endpoints as `Depends()` |
| `get_display_name(api_key, session)` | Jobs, leaderboard, registration routers |
| `add_to_leaderboard(user_id, input, score, solved, session)` | `POST /submit` |
| `get_leaderboard(session)` | `GET /leaderboard` |

## `app/core/job_manager.py`

All job CRUD operations. Each function takes an explicit `Session` argument.

| Function | Purpose |
|----------|---------|
| `create_job(user_id, input_data, session)` | INSERT Job, return job_id |
| `get_job(job_id, session)` | SELECT by id, return dict |
| `complete_job(job_id, result, session)` | UPDATE status + result_json |
| `charge_validation_quota(user_id, session)` | COUNT jobs, raise RuntimeError if at limit |
| `get_quota_info(user_id, session)` | Return `{used, limit, remaining}` |
| `make_json_safe(obj)` | Recursively convert numpy types; replace inf/nan with `failure_score` |
| `set_max_validations_per_user(limit)` | Called by `task_loader` after loading task |

## `app/core/task_loader.py`

Dynamically imports `app.tasks.<SLACATHON_ACTIVE_TASK>`. Validates presence of all required protocol attributes. Raises `RuntimeError` with a descriptive message if the module is missing or incomplete. Result is cached in a module-level variable after first call.

## `app/routers/jobs.py`

Implements `/validate`, `/submit`, `/jobs/{job_id}`. The `run_validation_job` background task opens its own `Session(engine)` because it runs outside the request lifecycle.

## `app/routers/leaderboard.py`

Implements `/leaderboard`, `/task`, `/history`. All three inject `session: DBSession = Depends(get_session)`. `/history` returns the `input_json` of the user's most recent N Job rows (ordered by `created_at` desc).

## `app/routers/registration.py`

Implements the email registration flow. Uses a separate `Jinja2Templates` instance pointed at `app/page_templates/` (CRT-themed forms), distinct from the main `app/templates/` used by `main.py`.

## `app/captcha.py`

Thin wrapper around the `altcha` library. `create_challenge()` generates a proof-of-work challenge; `verify_captcha(payload)` decodes and verifies the base64 JSON solution.

## `app/email_service.py`

Async email via `aiosmtplib`. Templates rendered with Jinja2 from `app/email_templates/`. Two functions: `send_verification_email` and `send_api_key_email`.
