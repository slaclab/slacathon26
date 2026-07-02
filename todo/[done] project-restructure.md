# Project Restructure Plan

Moves flat-root layout to a standard FastAPI package layout.  
Done alongside (or before) the user-registration feature — registration new files land in the new structure directly.

---

## Current Layout (flat, everything in root)

```
slacathon26/
├── main.py
├── middleware.py
├── job_manager.py
├── task_loader.py
├── settings.py
├── start.sh
├── Dockerfile
├── requirements.txt
├── index.html
├── leaderboard.html
├── team.html
├── tasks/
│   ├── __init__.py
│   ├── base.py
│   ├── flat_beam.py
│   └── fort.1
├── GPOptimizer.py
├── XoptOptimizer.py
├── GP-optimizer.ipynb
├── Xopt-optimizer.ipynb
├── usage.py
├── optimize_usage.py
├── optimize_xopt_usage.py
├── todo/
└── .devcontainer/
```

Problems:
- All server modules at root — no separation between app code, routing, data, templates
- Client examples mixed with server code
- HTML pages hardcoded as root files loaded by `main.py` open()
- No `app/` package — `import settings` works by accident of cwd, not by design

---

## Target Layout

```
slacathon26/
├── app/                          # server package
│   ├── __init__.py
│   ├── main.py                   ← was: main.py
│   ├── settings.py               ← was: settings.py
│   ├── db.py                     ← new (registration)
│   ├── captcha.py                ← new (registration)
│   ├── email_service.py          ← new (registration)
│   │
│   ├── core/                     # shared primitives
│   │   ├── __init__.py
│   │   ├── job_manager.py        ← was: job_manager.py
│   │   ├── middleware.py         ← was: middleware.py
│   │   └── task_loader.py        ← was: task_loader.py
│   │
│   ├── models/                   # SQLModel / data models
│   │   ├── __init__.py
│   │   └── user.py               ← new (registration)
│   │
│   ├── routers/                  # FastAPI APIRouters
│   │   ├── __init__.py
│   │   ├── jobs.py               ← extracted from main.py (/validate, /submit, /jobs)
│   │   ├── leaderboard.py        ← extracted from main.py (/leaderboard, /task)
│   │   └── registration.py       ← new (registration)
│   │
│   ├── tasks/                    ← was: tasks/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── flat_beam.py
│   │   └── fort.1
│   │
│   ├── templates/                # all Jinja2 templates
│   │   ├── pages/                # full HTML pages served by FastAPI
│   │   │   ├── _base_crt.html.j2
│   │   │   ├── index.html        ← was: index.html (static, no templating needed yet)
│   │   │   ├── leaderboard.html  ← was: leaderboard.html
│   │   │   ├── team.html         ← was: team.html
│   │   │   ├── register.html.j2  ← new (registration)
│   │   │   └── verify.html.j2    ← new (registration)
│   │   └── email/                # email templates
│   │       ├── verify_email.html.j2       ← new (registration)
│   │       └── api_key_delivery.html.j2   ← new (registration)
│   │
│   └── static/                   # future: CSS, images, favicons (empty for now)
│       └── .gitkeep
│
├── examples/                     # client examples — not part of server
│   ├── GPOptimizer.py            ← was: GPOptimizer.py
│   ├── XoptOptimizer.py          ← was: XoptOptimizer.py
│   ├── GP-optimizer.ipynb        ← was: GP-optimizer.ipynb
│   ├── Xopt-optimizer.ipynb      ← was: Xopt-optimizer.ipynb
│   ├── usage.py                  ← was: usage.py
│   ├── optimize_usage.py         ← was: optimize_usage.py
│   └── optimize_xopt_usage.py    ← was: optimize_xopt_usage.py
│
├── data/                         # runtime-generated files (git-ignored)
│   ├── .gitkeep
│   ├── leaderboard.json          ← was: leaderboard.json (root)
│   ├── jobs.json                 ← was: jobs.json (root)
│   ├── user_names.json           ← was: user_names.json (root) — removed after DB migration
│   └── slacathon.db              ← new: SQLite database
│
├── docker-compose.yml            ← new (registration)
├── Dockerfile                    ← update WORKDIR/CMD paths
├── start.sh                      ← update module path: app.main:app
├── requirements.txt
├── .env.example                  ← new: template for local config
├── .gitignore                    ← add data/*.json, data/*.db
├── .devcontainer/
│   └── devcontainer.json         ← update to use docker-compose
├── todo/
├── AGENTS.md                     ← update module paths in docs
└── README.md
```

---

## Move Table

| From (root) | To | Notes |
|---|---|---|
| `main.py` | `app/main.py` | Routes extracted to routers; only app init remains |
| `settings.py` | `app/settings.py` | Add new SMTP/DB/captcha vars |
| `middleware.py` | `app/core/middleware.py` | DB migration per registration plan |
| `job_manager.py` | `app/core/job_manager.py` | Update file path to `data/jobs.json` |
| `task_loader.py` | `app/core/task_loader.py` | Update import path `app.tasks.*` |
| `tasks/` | `app/tasks/` | No changes inside |
| `index.html` | `app/templates/pages/index.html` | `main.py` uses `Jinja2Templates` instead of `open()` |
| `leaderboard.html` | `app/templates/pages/leaderboard.html` | Same |
| `team.html` | `app/templates/pages/team.html` | Same |
| `GPOptimizer.py` | `examples/GPOptimizer.py` | Client example |
| `XoptOptimizer.py` | `examples/XoptOptimizer.py` | Client example |
| `GP-optimizer.ipynb` | `examples/GP-optimizer.ipynb` | Client example |
| `Xopt-optimizer.ipynb` | `examples/Xopt-optimizer.ipynb` | Client example |
| `usage.py` | `examples/usage.py` | Client example |
| `optimize_usage.py` | `examples/optimize_usage.py` | Client example |
| `optimize_xopt_usage.py` | `examples/optimize_xopt_usage.py` | Client example |
| `leaderboard.json` (root) | `data/leaderboard.json` | Update `settings.leaderboard_file` default |
| `jobs.json` (root) | `data/jobs.json` | Update `settings.jobs_file` default |
| `user_names.json` (root) | removed | Replaced by DB after registration migration |

---

## Key Code Changes

### `start.sh` and `Dockerfile`

```bash
# start.sh — update app module reference
gunicorn app.main:app ...

# Dockerfile
WORKDIR /workspace
CMD ["./start.sh"]
```

### `app/main.py` — slim down, use `Jinja2Templates`

```python
from fastapi.templating import Jinja2Templates
from app.routers import jobs, leaderboard, registration

templates = Jinja2Templates(directory="app/templates")

app.include_router(jobs.router)
app.include_router(leaderboard.router)
app.include_router(registration.router)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("pages/index.html", {"request": request})
```

Remove the three `open("*.html")` calls at module startup.

### `app/routers/jobs.py`

Extract from `main.py`:
- `POST /validate`
- `POST /submit`
- `GET /jobs/{job_id}`

### `app/routers/leaderboard.py`

Extract from `main.py`:
- `GET /leaderboard`
- `GET /task`
- `GET /board` (redirect)
- `GET /team`

### `settings.py` — path defaults

```python
leaderboard_file: str = Field(default="data/leaderboard.json")
jobs_file: str        = Field(default="data/jobs.json")
db_url: str           = Field(default="sqlite:///data/slacathon.db")
```

### `.gitignore` additions

```
data/*.json
data/*.db
data/*.ndjson
venv/
__pycache__/
*.pyc
.env
```

### `.env.example` (new)

```
SLACATHON_ACTIVE_TASK=flat_beam
SLACATHON_ROOT_PATH=/slacathon26
SLACATHON_PORT=8000
SLACATHON_SMTP_HOST=localhost
SLACATHON_SMTP_PORT=1025
SLACATHON_SMTP_FROM=noreply@slacathon26.local
SLACATHON_PUBLIC_URL=http://localhost:8000
SLACATHON_HCAPTCHA_SITE_KEY=10000000-ffff-ffff-ffff-000000000001
SLACATHON_HCAPTCHA_SECRET_KEY=0x0000000000000000000000000000000000000000
SLACATHON_VERIFY_TIMEOUT_HOURS=24
SLACATHON_CLEANUP_INTERVAL_MINUTES=10
```

---

## Implementation Order

Do restructure **before** registration feature to avoid double-touching files.

1. Create `app/`, `app/core/`, `app/models/`, `app/routers/`, `app/templates/pages/`, `app/templates/email/`, `app/static/`, `examples/`, `data/` directories
2. Move server files → `app/` and `app/core/` (update all internal imports)
3. Move HTML files → `app/templates/pages/`; switch `main.py` to `Jinja2Templates`
4. Extract routers from `main.py` → `app/routers/jobs.py` + `app/routers/leaderboard.py`
5. Move client examples → `examples/`
6. Update `settings.py` file-path defaults to `data/`
7. Update `start.sh`, `Dockerfile`, `AGENTS.md`
8. Add `data/.gitkeep`, `.env.example`, update `.gitignore`
9. Run server, verify all existing routes still work
10. Then implement registration feature into the new structure

---

## What Does NOT Change

- `tasks/` internal code — zero logic changes, just moves to `app/tasks/`
- API contract — all URLs, request/response shapes identical
- `leaderboard.json` / `jobs.json` content format — only path changes
- `.devcontainer/` — updated separately as part of registration plan
