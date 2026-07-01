# SLACATHON'26 DEMO - AI optimization platform for accelerators

Framework for hosting AI optimization hackathons (e.g. beam physics challenges).

Supports **pluggable tasks** via the `tasks/` directory. Switch the active task with the `SLACATHON_ACTIVE_TASK` environment variable (or in `.env`, defaults to `flat_beam`).

Each task defines:
- Input schema (Pydantic)
- `TARGET`, `MINIMIZE` (for solved determination)
- `FAILURE_SCORE`, `MAX_VALIDATIONS_PER_USER`

- Discover full task info at `GET /task` (schema, labels, bounds, target, minimize, etc.)
- Dynamic validation using per-task Pydantic models
- Example: Beamline Guru (default)

See the live site and GPOptimizer client for usage examples.

## Installation

### 1. Clone
```bash
git clone https://github.com/balticfish/slacathon26.git
cd slacathon26
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
./start.sh
```

Or for development:
```bash
source venv/bin/activate
uvicorn main:app --reload
```

**Note:** `start.sh` hard-codes the venv path for the current deployment. Edit it or use your own activation for other environments. Use `SLACATHON_ACTIVE_TASK` (or set it in `.env`) to switch challenge logic (see `tasks/`). All configuration uses the `SLACATHON_` prefix.

## Project Structure

```
backend/
├── main.py                 # FastAPI app (root_path=/slacathon26)
├── settings.py             # Centralized config via SLACATHON_* env vars + .env (pydantic-settings)
├── job_manager.py          # Job persistence (ndjson), quotas, validation counts, make_json_safe
├── middleware.py           # API key auth, per-user history tracker, leaderboard logic
├── task_loader.py          # Loads active task from tasks/ dir (enforces Task protocol)
├── tasks/
│   ├── base.py             # TaskInput, TaskResult, Task protocol (TARGET, MINIMIZE, FAILURE_SCORE, ...)
│   ├── flat_beam.py        # Default task (RTFB round-to-flat beam optimization)
│   ├── fort.1              # Physics data file (for flat beam task)
│   └── __init__.py
├── GPOptimizer.py          # Gaussian Process optimizer client example
├── optimize_usage.py       # Optimization script example (with input patching)
├── usage.py                # Simple validation client example
├── start.sh                # Launcher (activates venv + gunicorn, respects SLACATHON_*)
├── .env.example
├── index.html              # Landing / hero page
├── leaderboard.html        # Leaderboard UI (dynamic labels + target via /task)
├── team.html
├── .gitignore
└── README.md
```

**Key changes to project structure:**
- `models.py` and `logic.py` removed (dead code cleaned)
- New `settings.py` (pydantic-settings with `SLACATHON_` prefix) + `.env.example`
- `task_loader.py` + `tasks/` package for pluggable challenges (tasks declare TARGET, MINIMIZE, MAX_VALIDATIONS_PER_USER, etc.)
- `job_manager.py` extracted (jobs + quota logic moved out of middleware)
- Score is the raw optimization value from the task; TARGET + MINIMIZE only determine "solved"
- All static HTML served from root
- No top-level `app/` directory (flat `backend/` layout)

## Development

```bash
# Recommended: use the provided start.sh (or manually)
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Configuration is read from `.env` or environment variables with the `SLACATHON_` prefix.
```

To see the currently loaded task configuration:
```bash
curl http://localhost:8888/task
```

## Production

Use the included launcher (recommended):

```bash
./start.sh
```

It activates the venv and runs:
```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 1 --timeout 300 \
  --bind 127.0.0.1:8888 main:app
```

To switch tasks (pluggable system):

```bash
export SLACATHON_ACTIVE_TASK=flat_beam   # or fel, mars, etc. (see tasks/ dir)
./start.sh
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
- 🔌 Pluggable tasks (`tasks/*.py` + `SLACATHON_ACTIVE_TASK`)
- 📊 Dynamic input schema (`GET /task`)
- 📈 Job-based validation + full history
- 🏆 Leaderboard with duplicate detection
- 🧪 Example GP optimizer client (GPOptimizer.py)

## License

Stanford License

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Support

For questions or issues, please open an issue on GitHub or contact the team.
