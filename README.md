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

## Installation

### 1. Clone
```bash
git clone https://github.com/balticfish/slacathon26.git
cd slacathon26   # this is SLACathon v0.1 (Tabby)
```

### 2. Virtualenv
```bash
python -m venv venv
source venv/bin/activate
pip install numpy scipy fastapi uvicorn gunicorn
```

### 3. Configuration
```bash
cp .env.example .env
# Edit .env and set at minimum:
#   SLACATHON_API_KEYS=your_strong_key_1,your_strong_key_2
#   SLACATHON_ACTIVE_TASK=flat_beam
```

All settings use the `SLACATHON_` prefix (see `.env.example` for full list: keys, host/port, files, limits, root_path, etc.).

### 4. Run
```bash
./scripts/start.sh
```

Or for development:
```bash
source venv/bin/activate
PYTHONPATH=src uvicorn slacathon.main:app --reload
```

**Note:** `scripts/start.sh` is relocatable (derives ROOT, sets PYTHONPATH, cds to root, sources .env from root). Use `SLACATHON_ACTIVE_TASK` (or set it in `.env`) to switch challenge logic (see `src/slacathon/tasks/`). All configuration uses the `SLACATHON_` prefix.

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
│       ├── main.py
│       ├── settings.py
│       ├── middleware.py
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
│   └── team.html
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

## Development

```bash
# Recommended: use the provided scripts/start.sh (or manually)
source venv/bin/activate
PYTHONPATH=src uvicorn slacathon.main:app --reload --host 0.0.0.0 --port 8000
```

Configuration is read from `.env` or environment variables with the `SLACATHON_` prefix.
```

To see the currently loaded task configuration:
```bash
curl http://localhost:8888/task
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
- **Leaderboard:** `https://your-domain.com/slacathon26/board`
- **Team Page:** `https://your-domain.com/slacathon26/team`
- **Task Info:** `GET https://your-domain.com/slacathon26/task` (schema + target/minimize/quotas)
- **Validate (async job):** `POST https://your-domain.com/slacathon26/validate` (returns `job_id` + `quota`)
- **Job result:** `GET /jobs/{job_id}` (includes `quota`)
- **Submit to leaderboard:** `POST https://your-domain.com/slacathon26/submit`
- **History / Leaderboard:** `GET /history`, `GET /leaderboard`

Use `X-API-Key` header for protected endpoints. Quota limits (`MAX_VALIDATIONS_PER_USER`) and scoring rules come from the active task.

## Features

- 🚀 FastAPI + Gunicorn
- 🔐 API key authentication + per-user quotas
- 🔌 Pluggable tasks (`src/slacathon/tasks/*.py` + `SLACATHON_ACTIVE_TASK`)
- 📊 Dynamic input schema (`GET /task`)
- 📈 Job-based validation + full history
- 🏆 Leaderboard with duplicate detection
- 🧪 Example optimizer clients: clients/gp_optimizer.py and clients/xopt_optimizer.py
```

## License

Stanford License

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Support

For questions or issues, please open an issue on GitHub or contact the team.
