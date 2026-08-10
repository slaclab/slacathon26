# Local Development Setup

## Devcontainer (recommended)

The repo ships a VS Code devcontainer that starts the app and Mailpit together.

**Requirements:** Docker Desktop, VS Code + Dev Containers extension.

1. Open the repo folder in VS Code.
2. Click **Reopen in Container** when prompted.
3. The container builds and starts; VS Code drops you inside.
4. Press **F5** (Run → **Run: FastAPI dev**) to start uvicorn with `--reload`.

Ports automatically forwarded:
- `8000` — app
- `8025` — Mailpit inbox UI

`SLACATHON_SMTP_HOST` and `SLACATHON_SMTP_PORT` are pre-configured in `docker-compose.yml`.

---

## Manual Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

Start Mailpit (needed for registration):

```bash
docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit:latest
```

Start the server:

```bash
PYTHONPATH=src uvicorn slacathon.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

---

## Source Layout

```
src/slacathon/
├── main.py           # all FastAPI routes
├── settings.py       # pydantic-settings, SLACATHON_ prefix
├── db.py             # SQLite CRUD (users, jobs, quota_charges)
├── job_manager.py    # job lifecycle + quota enforcement
├── middleware.py     # API key auth, leaderboard logic
├── captcha.py        # Altcha PoW challenge/verify
├── email_service.py  # async SMTP send helpers
├── task_loader.py    # loads SLACATHON_ACTIVE_TASK module
└── tasks/
    ├── base.py       # Task protocol + base models
    ├── flat_beam.py  # default task (local, no network)
    ├── fel.py        # FEL pulse intensity (calls SLAC ARD)
    ├── cuinj.py      # LCLS CU injector emittance (calls SLAC ARD)
    └── data/fort.1   # beam distribution data for flat_beam
```

## Runtime Data

Files in `data/` are created on first run and are gitignored:

| File | Content |
|---|---|
| `data/slacathon.db` | SQLite: `users`, `jobs`, `quota_charges` tables |
| `data/leaderboard.json` | Top-15 leaderboard (plain JSON) |

Reset for a clean slate:

```bash
rm -f data/slacathon.db data/leaderboard.json
```

## Hot Reload

`--reload` flag watches `src/` for changes. Task modules are loaded once at startup (`TASK = load_active_task()`); changing a task file requires a server restart.
