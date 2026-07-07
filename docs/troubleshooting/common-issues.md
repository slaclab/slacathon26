# Common Issues

## Server won't start

**`ModuleNotFoundError: No module named 'app'`**

Run the server from the project root (the directory containing `app/`):

```bash
cd /path/to/slacathon26
uvicorn app.main:app --reload
```

---

**`RuntimeError: Task module 'flat_beam' failed to load`**

Check that `app/tasks/flat_beam.py` exists and implements all required protocol attributes. See [Task Development Guide](../guides/task-development.md) for the full list.

---

**`sqlite3.OperationalError: no such table: ...`**

Tables are created by `create_db_and_tables()` on startup. If you're running tests, ensure the test fixture calls `SQLModel.metadata.create_all(engine)` before making requests.

---

## Registration / Email

**Verification email not received**

1. Check Mailpit web UI at `http://localhost:8025`
2. Verify `SLACATHON_SMTP_HOST` and `SLACATHON_SMTP_PORT` match the running SMTP server
3. Check server logs for `Failed to send verification email` — a `503` response means the email service is unreachable

---

**`410 Gone` on verification link**

The link expired. Unverified registrations are deleted after `SLACATHON_VERIFY_TIMEOUT_HOURS` (default 24h). Register again at `/register`.

---

## API Errors

**`401 Unauthorized`**

- Check the `X-API-Key` header is present and correct
- The key must belong to a verified user (check `User.verified = True` in DB)
- Dev keys `key_123`, `key_456`, `key_789` are seeded on first startup

---

**`429 Too Many Requests`**

Per-user quota exceeded. The current quota is set by the active task's `MAX_VALIDATIONS_PER_USER` (default 10,000). Contact the platform administrators for a quota reset.

---

**`422 Unprocessable Entity`**

Input validation failed. The active task's `Input` model uses `extra = "forbid"`. Check `/task` for valid parameter names and types.

---

**Job stuck in `processing`**

If a background job never completes, check server logs for errors in `run_validation_job`. The job will be marked as failed with `FAILURE_SCORE` if the task raises an exception.

---

## CAPTCHA

**`400 Bad Request` on registration**

The Altcha CAPTCHA solution is invalid or missing. Ensure `altcha.min.js` is loaded from `/static/altcha.min.js` and the `altcha-widget` element has the correct `challengeurl` attribute pointing to `/captcha-challenge`.

---

## Database

**`data/slacathon26.db` not created**

The `data/` directory must exist and be writable:

```bash
mkdir -p data
```

The DB file is created automatically by `SQLModel.metadata.create_all()` on first startup.
