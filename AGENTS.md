# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

SLACATHON'26 — a FastAPI-based AI optimization hackathon platform for accelerator physics challenges. Competitors submit beam physics parameter sets via API; the server evaluates them and maintains a leaderboard.

## Running the Server

Dev (auto-reload):
```bash
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
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

See `settings.py` for full list.

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

- **`main.py`** — FastAPI app; mounts all routes; HTML pages served inline at startup
- **`settings.py`** — Pydantic-settings singleton (`settings`); all `SLACATHON_*` env vars
- **`task_loader.py`** — Imports and caches the active task module once; enforces required attributes
- **`middleware.py`** — API key auth, leaderboard persistence (`leaderboard.json`), `UserSubmissionTracker` (in-memory recent history per user), `user_names.json` mapping
- **`job_manager.py`** — Job lifecycle (ndjson append-only `jobs.json`), per-user quota tracking, `make_json_safe` for numpy types

### Pluggable Task System

Tasks live in `tasks/<name>.py`. Each module must export:

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

- `leaderboard.json` — JSON array, rewritten on each update; top `LEADERBOARD_SIZE` entries sorted by score
- `jobs.json` — ndjson (one record per line, appended); last 300 lines loaded into memory at startup; quota counts rebuilt by scanning full file on startup
- `user_names.json` — API key → display name mapping

### Quota Logic

`job_manager.charge_validation_quota` is the single gating primitive used by both `/validate` and `/submit`. It checks current count, appends the record durably, then increments the in-memory counter — count only rises after successful disk write.

## Optimizer Client Examples

- `GPOptimizer.py` — Gaussian Process (sklearn) optimizer; requires `numpy scipy scikit-learn`
- `XoptOptimizer.py` — Xopt Bayesian optimizer; requires `xopt numpy requests`
- `usage.py` / `optimize_usage.py` / `optimize_xopt_usage.py` — standalone usage scripts

These are client examples for hackathon participants, not part of the server.
