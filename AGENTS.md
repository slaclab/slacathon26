# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

SLACATHON'26 — a FastAPI-based AI optimization hackathon platform for accelerator physics challenges. Competitors submit beam physics parameter sets via API; the server evaluates them and maintains a leaderboard.

## Running the Server

Dev (auto-reload):
```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production:
```bash
./start.sh   # gunicorn + uvicorn worker on 127.0.0.1:8888
```

Check active task config:
```bash
curl http://localhost:8888/slacathon26/task
```

Switch tasks without code changes:
```bash
export SLACATHON_ACTIVE_TASK=flat_beam
./start.sh
```

## Configuration

All settings use `SLACATHON_` prefix, loaded from `.env` or environment. Key vars:
- `SLACATHON_API_KEYS` — comma/space-separated valid API keys (falls back to hardcoded dev keys if unset)
- `SLACATHON_ACTIVE_TASK` — task module name in `tasks/` (default: `flat_beam`)
- `SLACATHON_ROOT_PATH` — FastAPI root path (default: `/slacathon26`)
- `SLACATHON_PORT` — server port (default: `8888`)

See `app/settings.py` for full list.

## Architecture

### Request Flow

```
POST /validate  →  verify_api_key (middleware.py)
                →  charge_validation_quota (job_manager.py)  [raises 429 if over limit]
                →  create_job → asyncio background task
                →  run_validation_job → TASK.validate() → complete_job
GET /jobs/{id}  →  returns result when status=="completed"

POST /submit    →  same quota charge path → TASK.validate() → add_to_leaderboard
```

### Key Modules

- **`app/main.py`** — FastAPI app; mounts all routes; HTML pages via Jinja2Templates
- **`app/settings.py`** — Pydantic-settings singleton (`settings`); all `SLACATHON_*` env vars
- **`app/core/task_loader.py`** — Imports and caches the active task module once; enforces required attributes
- **`app/core/middleware.py`** — API key auth, leaderboard persistence (`data/leaderboard.json`), `UserSubmissionTracker` (in-memory recent history per user), `data/user_names.json` mapping
- **`app/core/job_manager.py`** — Job lifecycle (ndjson append-only `data/jobs.json`), per-user quota tracking, `make_json_safe` for numpy types
- **`app/routers/jobs.py`** — `POST /validate`, `POST /submit`, `GET /jobs/{job_id}`
- **`app/routers/leaderboard.py`** — `GET /leaderboard`, `GET /task`, `GET /history`

### Pluggable Task System

Tasks live in `app/tasks/<name>.py`. Each module must export:

| Attribute | Type | Purpose |
|---|---|---|
| `Input` | Pydantic model | Validated input schema |
| `Result` | Pydantic model | Must have `score`, `solved`, `message`, `evaltime` |
| `TASK_NAME` | str | Display name |
| `INPUT_LABELS` | list[str] | Human-readable param names |
| `BOUNDS` | list[tuple] | `[(min, max), ...]` per input |
| `TARGET` | float | Score threshold for "solved" |
| `MINIMIZE` | bool | True = lower score is better |
| `FAILURE_SCORE` | float | Score returned on error |
| `MAX_VALIDATIONS_PER_USER` | int | Per-user quota |
| `validate(data: Input) -> Result` | function | Core evaluation |

The current task is the `flat_beam` task (Round-To-Flat Beam optics): 5 skew quadrupole/drift parameters (`q1, q2, q3, d2, d3`) optimizing x-y coupling in a beam transport matrix.

### Persistence

- `data/leaderboard.json` — JSON array, rewritten on each update; top `LEADERBOARD_SIZE` entries sorted by score
- `data/jobs.json` — ndjson (one record per line, appended); last 300 lines loaded into memory at startup; quota counts rebuilt by scanning full file on startup
- `data/user_names.json` — API key → display name mapping

### Quota Logic

`job_manager.charge_validation_quota` is the single gating primitive used by both `/validate` and `/submit`. It checks current count, appends the record durably, then increments the in-memory counter — count only rises after successful disk write.

## Todo / Implementation Plans

Plans live in `todo/`. Each file describes a single implementation phase with code, acceptance criteria, and a test suite.

**After implementing a phase**, mark it done by renaming the file with a `[done]-` prefix:

```
todo/<task>/work-to-do.md
→
todo/<task>/[done]-work-to-do.md
```

Agents must rename the file as the final step of implementing any phase plan.

---

## Optimizer Client Examples

In `examples/`:
- `GPOptimizer.py` — Gaussian Process (sklearn) optimizer; requires `numpy scipy scikit-learn`
- `XoptOptimizer.py` — Xopt Bayesian optimizer; requires `xopt numpy requests`
- `usage.py` / `optimize_usage.py` / `optimize_xopt_usage.py` — standalone usage scripts

These are client examples for hackathon participants, not part of the server.
