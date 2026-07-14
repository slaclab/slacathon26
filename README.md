# SLACathon v0.1 (Tabby) - online platform for accelerator hackathons

**SLACathon v0.1 (Tabby)** is a framework for hosting AI optimization hackathons (e.g. beam physics challenges).

**Versioning & Codenames**

- **v0.1 — Tabby** (current)
- **v0.2 — Snowshoe** (upcoming)
- **v0.3 — Mau** (future)

Supports **pluggable tasks** via the `tasks/` directory. Switch the active task with the `SLACATHON_ACTIVE_TASK` environment variable (or in `.env`, defaults to `flat_beam`).

Each task defines:
- Input schema (Pydantic)
- `TARGET`, `MINIMIZE` (for solved determination)
- `FAILURE_SCORE`, `MAX_VALIDATIONS_PER_USER`

- Discover full task info at `GET /task` (schema, labels, bounds, target, minimize, etc.)
- Dynamic validation using per-task Pydantic models
- Example: Beamline Guru (default)

See the live site and optimizer clients (in clients/) for usage examples.

**Optimizer examples dependencies:**
- `clients/gp_optimizer.py`: `pip install numpy scipy scikit-learn`
- `clients/xopt_optimizer.py`: `pip install xopt numpy requests` (Xopt provides modern Bayesian optimization)

## Authors

- A. Halavanau (SLAC)
- C.J. Takacs (ex-SLAC)
- Claude Code
- Grok Build

## Development (Devcontainer — recommended)

The repo ships a VS Code devcontainer that starts the app and a local mail server (Mailpit) together.

### Prerequisites
- Docker Desktop
- VS Code with the **Dev Containers** extension

### Start

1. Open the repo folder in VS Code.
2. When prompted, click **Reopen in Container** (or run `Dev Containers: Rebuild and Reopen in Container`).
3. VS Code builds the image, starts `app` + `mailpit` via `docker-compose.yml`, and drops you into the container.
4. Press **F5** (or Run → **Run: FastAPI dev**) to start uvicorn with `--reload`.
5. App: `http://localhost:8000/slacathon26/`  
   Mailpit UI (inspect outgoing emails): `http://localhost:8025`

Environment is configured automatically inside the container — `SLACATHON_SMTP_HOST=mailpit`, port 1025.

## Installation (local, no Docker)

### 1. Clone
```bash
git clone https://github.com/balticfish/slacathon26.git
cd slacathon26
```

### 2. Install
```bash
python -m venv venv
source venv/bin/activate
pip install -e .
```

### 3. Configuration
```bash
cp .env.example .env
# Edit .env — required for self-registration:
#   SLACATHON_PUBLIC_URL=https://your-domain.com
#   SLACATHON_SMTP_HOST=your-smtp-host
#   SLACATHON_SMTP_PORT=587
#   SLACATHON_SMTP_FROM=noreply@your-domain.com
#   SLACATHON_ALTCHA_HMAC_KEY=<random secret>
```

All settings use the `SLACATHON_` prefix (see `.env.example` for the full list).

### 4. Run
```bash
PYTHONPATH=src uvicorn slacathon.main:app --reload
```

## Project Structure

```
SLACathon-v0.1-Tabby/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── src/
│   └── slacathon/
│       ├── __init__.py
│       ├── main.py           # routes (API + registration)
│       ├── settings.py
│       ├── middleware.py
│       ├── db.py             # SQLite helpers
│       ├── captcha.py        # Altcha PoW CAPTCHA
│       ├── email_service.py  # async SMTP
│       ├── job_manager.py
│       ├── task_loader.py
│       └── tasks/
│           ├── __init__.py
│           ├── base.py
│           ├── flat_beam.py
│           └── data/
│               └── fort.1
│
├── clients/
│   ├── README.md
│   ├── gp_optimizer.py
│   ├── xopt_optimizer.py
│   ├── optimize_usage.py
│   ├── optimize_xopt_usage.py
│   └── usage.py
│
├── notebooks/
│   ├── GP-optimizer.ipynb
│   └── Xopt-optimizer.ipynb
│
├── web/
│   ├── index.html
│   ├── leaderboard.html
│   ├── team.html
│   ├── static/
│   │   └── altcha.min.js
│   ├── page_templates/       # Jinja2 templates (registration UI)
│   └── email_templates/      # Jinja2 templates (verification + API key emails)
│
├── scripts/
│   └── start.sh
│
├── data/
│   ├── slacathon.db          # jobs + users/quota (SQLite, gitignored)
│   └── leaderboard.json      # top-15 only (still plain JSON)
│
└── tests/
    ├── test_quota.py
    ├── test_leaderboard.py
    └── test_flat_beam.py
```

**Key changes to project structure:**
- `models.py` and `logic.py` removed (dead code cleaned)
- New `settings.py` (pydantic-settings with `SLACATHON_` prefix) + `.env.example`
- `task_loader.py` + `tasks/` package for pluggable challenges (tasks declare TARGET, MINIMIZE, MAX_VALIDATIONS_PER_USER, etc.)
- `job_manager.py` extracted (jobs + quota logic moved out of middleware)
- Score is the raw optimization value from the task; TARGET + MINIMIZE only determine "solved"
- Client examples moved to `clients/` (separate from server)
- Runtime data to `data/` (gitignored): `slacathon.db` for jobs+users+quota, `leaderboard.json` remains simple JSON
- `fort.1` moved to data subdir under tasks, loaded via importlib.resources
- Structure now uses src/ layout for the SLACathon package

## User Registration

Participants self-register via the web UI — no admin key seeding required.

### Flow

1. Visit `/slacathon26/register` → fill in email + display name + CAPTCHA → submit.
2. Receive a verification email with a one-time link (expires in `SLACATHON_VERIFY_TIMEOUT_HOURS`, default 24 h).
3. Click the link → solve CAPTCHA → email verified.
4. Receive a second email containing your API key.
5. Use the key as `X-API-Key: <key>` on all protected endpoints.

Lost your key? Visit `/slacathon26/resend-key` to have it resent.

### Registration endpoints

| Endpoint | Description |
|---|---|
| `GET /register` | Registration form |
| `POST /register` | Submit email + display name |
| `GET /verify?token=…` | Email verification form |
| `POST /verify` | Verify token → receive API key |
| `GET /registered` | Confirmation page |
| `GET /resend-key` | API key resend form |
| `POST /resend-key` | Resend API key to verified address |
| `GET /captcha-challenge` | CAPTCHA challenge (Altcha PoW) |

### Required settings for email delivery

```env
SLACATHON_PUBLIC_URL=https://your-domain.com     # base URL for verification links
SLACATHON_SMTP_HOST=your-smtp-host
SLACATHON_SMTP_PORT=587
SLACATHON_SMTP_FROM=noreply@your-domain.com
SLACATHON_ALTCHA_HMAC_KEY=<random secret>        # CAPTCHA signing key
```

In the devcontainer these are pre-configured to use the bundled Mailpit service.

## Development

To see the currently loaded task configuration:
```bash
curl http://localhost:8000/slacathon26/task
```

### Storage & Migration

Jobs, validation quota, and user (API key + display name) data live in `data/slacathon.db` (SQLite).

The leaderboard is intentionally kept as a small plain JSON file (`data/leaderboard.json`).

If you are upgrading from an older version that used the NDJSON/JSON files, run the one-time migration:

```bash
python scripts/migrate_to_sqlite.py
```

This backs up the old files and populates the database. `leaderboard.json` is never modified by the migration.

## Production

Use the included launcher (recommended):

```bash
./scripts/start.sh
```

It activates the venv and runs:
```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 1 --timeout 300 \
  --bind 127.0.0.1:8888 slacathon.main:app
```
(or simply `./scripts/start.sh`)

To switch tasks (pluggable system):

```bash
export SLACATHON_ACTIVE_TASK=flat_beam   # or fel, mars, etc. (see src/slacathon/tasks/ dir)
./scripts/start.sh
```

Or set it in `.env`:
```env
SLACATHON_ACTIVE_TASK=flat_beam
```

`GET /task` returns the current task's input schema, parameter labels, bounds, **target**, **minimize** direction, `failure_score`, and `max_validations_per_user`. Tasks define these values.

## Accessing the Application

The app is mounted under `/slacathon26` (FastAPI `root_path`).

- **Landing Page:** `https://your-domain.com/slacathon26/`
- **Register:** `https://your-domain.com/slacathon26/register`
- **Get API Key:** `https://your-domain.com/slacathon26/resend-key`
- **Leaderboard:** `https://your-domain.com/slacathon26/board`
- **Team Page:** `https://your-domain.com/slacathon26/team`
- **Task Info:** `GET https://your-domain.com/slacathon26/task` (schema + target/minimize/quotas)
- **Validate (async job):** `POST https://your-domain.com/slacathon26/validate` (returns `job_id` + `quota`)
- **Job result:** `GET /jobs/{job_id}` (includes `quota`)
- **Submit to leaderboard:** `POST https://your-domain.com/slacathon26/submit`
- **History / Leaderboard:** `GET /history`, `GET /leaderboard`

Use `X-API-Key` header for protected endpoints. API keys are issued after email verification via the registration flow. Quota limits (`MAX_VALIDATIONS_PER_USER`) and scoring rules come from the active task.

## Features

- 🚀 FastAPI + Gunicorn
- 📝 Self-serve user registration with email verification + Altcha CAPTCHA
- 🔐 API key authentication + per-user quotas
- 🔌 Pluggable tasks (`src/slacathon/tasks/*.py` + `SLACATHON_ACTIVE_TASK`)
- 📊 Dynamic input schema (`GET /task`)
- 📈 Job-based validation + full history
- 🏆 Leaderboard with duplicate detection
- 🧪 Example optimizer clients: clients/gp_optimizer.py and clients/xopt_optimizer.py
- 🐳 VS Code devcontainer with Mailpit for local email testing
```

## License

Stanford License

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Support

For questions or issues, please open an issue on GitHub or contact the team.
