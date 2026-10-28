# Multi-problem abstraction: registry, per-task routing, job queue

## Context

App today loads exactly one task module at startup (`SLACATHON_ACTIVE_TASK`) into a `TASK` global in `main.py:63`; every endpoint reads it. Jobs are fire-and-forget `asyncio.create_task` with no queue; `jobs`/`quota_charges` tables have no task column; leaderboard already has `task_name` column but stores the settings string. Invalid user input returns 500 (pydantic `ValidationError` swallowed by `except Exception`), `/submit` charges quota before validating, bounds never enforced.

Goal: a `Problem` abstraction (check input → 422 on error; run inside job queue), auto-discovered registry of all task modules, human-readable `task_id` (module name: `flat_beam`, `fel`, `cuinj`) in URL paths, general leaderboard filterable by task, real per-task job queue with `queued` status + queue position, no per-user quota.

User decisions: URL-path routing with readable task_id; leaderboard general + filter; no quota, queue instead with "waiting" visibility; auto-discover all task modules; fix the three bugs.

## Design

| Decision | Choice |
|---|---|
| Abstraction | ABC `Problem` in `tasks/base.py`; each task module exposes `TASK = XxxProblem()`. Module-level `Input`/`Result`/`validate` kept for compat (`tests/test_flat_beam.py`). |
| Registry | `src/slacathon/registry.py`, eager `pkgutil.iter_modules(slacathon.tasks.__path__)`, skip `base`, `_*`, subpackages (`data`); require `module.TASK` isinstance `Problem`; `task_id` = module short name; `RuntimeError` fail-fast. |
| Queue | `src/slacathon/job_queue.py`: one `asyncio.Queue` + `MAX_CONCURRENCY` worker coroutines per task (default 1 → serial), `run_in_executor` on shared `ThreadPoolExecutor`. Started/stopped in FastAPI `lifespan`. `/submit` also enqueues and awaits a future (single code path, no loop blocking). |
| Status | `queued → processing → completed | failed`. `failed` only for exception from `run()`; task-level remote errors stay `completed` with failure score (current behaviour). |
| Quota | Remove `quota_charges`, `charge_*`, `MAX_VALIDATIONS_PER_USER`, setting `max_validations_per_user`. Keep `get_quota_info()` shim → `{"used": n, "limit": null, "remaining": null}` for client compat. |
| Legacy routes | Keep `/task`, `/validate`, `/submit` one release, routed to `settings.active_task` (now "default task"), `Deprecation: true` header. Configmap `fel` unchanged. |
| 422 shape | Pydantic-like list: `{"detail": [{"loc": ["input","q1"], "msg": "...", "type": "value_error.bounds"}]}`. |
| Leaderboard no filter | Flat list with `task_id` per row, each task sorted by own `minimize`; plus `tasks: {task_id: {name,target,minimize}}` map. |

## Steps

### 1. `src/slacathon/tasks/base.py` — Problem ABC
Keep `TaskInput`, `TaskResult`. Replace Protocol:
```python
class InputValidationError(ValueError):
    def __init__(self, errors: list[dict]): ...   # [{loc, msg, type}]

class Problem(ABC):
    task_id: str; TASK_NAME: str; INPUT_LABELS: list[str]; BOUNDS: list[tuple[float,float]]
    TARGET: float; MINIMIZE: bool = True; FAILURE_SCORE: float = 1e10; MAX_CONCURRENCY: int = 1
    Input: type[TaskInput] = TaskInput; Result: type[TaskResult] = TaskResult
    def check_input(self, raw: dict) -> TaskInput      # Input.model_validate + bounds over INPUT_LABELS (getattr or model_extra); raises InputValidationError; non-dict raw → error
    @abstractmethod
    def run(self, data: TaskInput) -> TaskResult
    def validate(self, data)                           # compat alias: dict → Input → run
    def metadata(self) -> dict                         # GET /tasks/{id} payload
    def failure_result(self, message: str) -> dict
```
Missing label on `extra=allow` models → no error (FEL fills defaults).

### 2. Task modules (minimal diff)
`flat_beam.py`, `fel.py`, `cuinj.py`: append subclass copying existing constants, `run()` delegates to existing `validate()`, `TASK = XxxProblem()`. Drop `MAX_VALIDATIONS_PER_USER`. `fel`/`cuinj` `MAX_CONCURRENCY = 4` (HTTP-bound). Optional follow-up: lazy `fort.1` via `cached_property`.

### 3. `src/slacathon/registry.py` (new)
`discover_tasks(package) -> dict[str, Problem]`, `get_registry()` (cached), `get_task(task_id)` (KeyError), `get_default_task_id()` (validates `settings.active_task` exists), `list_tasks()`. `task_loader.load_active_task()` becomes shim with `DeprecationWarning`, deleted in PR3. `main.py` dependency `task_dep(task_id)` → 404 `Unknown task '<id>'`.

### 4. `src/slacathon/middleware.py` — leaderboard by task_id
Remove `_get_task_info`. `add_to_leaderboard(user_id, task_id, input, score, solved)`; `minimize` from `get_task(task_id).MINIMIZE`; store `task_id` in `leaderboard.task_name` column. `get_leaderboard(task_id: str | None)`: filtered or concatenated per-task. `db.init_db()` backfill: `UPDATE leaderboard SET task_name=? WHERE task_name=''` with `settings.active_task` (idempotent).

### 5. `src/slacathon/main.py` — routing
Remove `TASK` global. Helper `_check_or_422(problem, body)` wraps `_extract_input_data` + `problem.check_input`.

| Method | Path | Notes |
|---|---|---|
| GET | `/tasks` | `{tasks:[metadata], default_task_id}` |
| GET | `/tasks/{task_id}` | `metadata()`; 404 unknown |
| POST | `/tasks/{task_id}/validate` | 422 bad input; enqueue; `{job_id, task_id, status:"queued", queue_position, message}` |
| POST | `/tasks/{task_id}/submit` | 422 first; await queue future; `add_to_leaderboard`; response + `task_id` |
| GET | `/tasks/{task_id}/queue` | `{task_id, queued, processing, max_concurrency}` |
| GET | `/leaderboard?task_id=` | 404 if unknown; `{total_entries, leaderboard, tasks}` |
| GET | `/jobs/{job_id}` | + `task_id`, `queue_position` (when queued), `started_at`, `error` (failed); `quota` shim |
| GET | `/history` | submissions carry `task_id` |
| GET/POST | `/task`, `/validate`, `/submit` | legacy → default task, `Deprecation` header |

Errors: `InputValidationError` → 422; `asyncio.QueueFull` → 503; submit timeout → 504; unexpected → 500 logged. No 429.

### 6. `src/slacathon/db.py` — migration
Guard: `PRAGMA table_info(jobs)` lacks `task_id` → in one transaction:
```sql
CREATE TABLE jobs_new (job_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL DEFAULT '',
  input_json TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT, error TEXT,
  created_at REAL, started_at REAL, completed_at REAL);   -- no CHECK; validated in Python
INSERT INTO jobs_new (job_id,user_id,task_id,input_json,status,result_json,created_at,completed_at)
  SELECT job_id,user_id,:default_task_id,input_json,status,result_json,created_at,completed_at FROM jobs;
DROP TABLE jobs; ALTER TABLE jobs_new RENAME TO jobs;
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_task_status ON jobs(task_id,status);
DROP TABLE IF EXISTS quota_charges;
```
Fresh-install `CREATE TABLE jobs` uses new schema. Functions: `load_jobs/insert_job/get_job` carry `task_id, started_at, error`; `update_job` allows `status,result,completed_at,started_at,error`; new `get_jobs_by_status(statuses)`, `count_jobs_by_user(user_id)`; delete `charge_quota`, `get_user_charge_count`.

### 7. `src/slacathon/job_manager.py`
Remove quota code + `MAX_VALIDATIONS_PER_USER`. `create_job(user_id, task_id, input_data)` status `queued`. Add `mark_processing(job_id)`, `fail_job(job_id, error)`. `get_quota_info` shim. Remove import-time `init_db(); load_jobs()` → called from `lifespan`.

### 8. `src/slacathon/job_queue.py` (new)
```python
@dataclass class QueuedJob: job_id, task_id, input_data, future: asyncio.Future | None
class TaskQueue:        # per problem
    start()/stop(); enqueue(job)->position; position(job_id); stats(); _worker(idx)
    # worker: get → mark_processing → run_in_executor(problem.run) → sleep(settings.job_completion_delay_seconds) → complete_job/fail_job → resolve future
    # pending OrderedDict[job_id, QueuedJob] for position()
class JobQueueManager:
    start() (executor max_workers=sum MAX_CONCURRENCY; TaskQueue per task; requeue_stuck_jobs()); stop()
    enqueue(task_id, job_id, input_data, *, wait=False)->(position, future|None)
    queue_position(task_id, job_id); stats(task_id)
    async requeue_stuck_jobs()  # queued/processing rows → reset queued → enqueue; unknown task_id → fail_job
```
Exposed via `app.state.job_queues`. New settings: `queue_max_size=1000`, `submit_timeout_seconds=120`, `job_completion_delay_seconds=1.0`; remove `max_validations_per_user`.

### 9. Tests
`conftest.py`: `api_key` fixture via `db.upsert_user`; `tests/fixtures/bad_tasks/` package (module without `TASK`). FEL/CUINJ: monkeypatch `session.post`.

- `test_registry.py`: discovers `{flat_beam,fel,cuinj}`; skips `base`/`data`; bad package → RuntimeError; bad default task → RuntimeError.
- `test_problem_base.py`: check_input ok; unknown field → `loc==["input","q9"]`; bounds → `value_error.bounds`; fel extra=allow bounds / missing knob ok.
- `test_tasks_api.py`: `/tasks` list; metadata; unknown 404 on all routes; validate 422 shape; validate→queued→completed; `task_id` + `quota.limit None`; queue positions 1,2,3 with slow `run`; submit 422 leaves leaderboard; submit ranks; other-user 403.
- `test_leaderboard.py`: filter by task; unfiltered has `task_id` rows.
- `test_legacy_routes.py`: `/task`, `/validate`, `/submit` default task + `Deprecation` header.
- `test_queue_recovery.py`: `processing` row requeued on start; exception → `failed` + `error`.
- `test_db_migration.py`: legacy `jobs` with CHECK → rebuilt, rows kept, `quota_charges` gone, idempotent.
- `test_quota.py` → `test_quota_info_unlimited`.

### 10. `web/leaderboard.html`
`BASE` from `window.location.pathname`; `<select id="task-select">` from `GET /tasks` (default `default_task_id`, `localStorage`, `?task_id=` override); dynamic `TARGET: SCORE ≤/≥ target`, name, labels from metadata; refresh uses selection.

### 11. Clients
`gp_optimizer.py`, `xopt_optimizer.py`: `task_id` arg / `--task-id` / env `SLACATHON_TASK_ID`; `/tasks/{id}` routes; `queued` pending, `completed|failed` terminal; submit timeout 180s. `usage.py` `TASK_ID`; fix `optimize_fel/cuinj.py` docstrings.

### 12. Docs/config
README, `docs/guides/writing-a-task.md` (subclass `Problem`, `TASK=`), architecture/config/deployment docs, `AGENTS.md` (quotas → job queue; `registry.py`, `job_queue.py`), `.env.example` new settings, configmap unchanged (`kubectl kustomize` both overlays).

## PR split
1. `feat(tasks)!: problem base class, registry, per-task routing` — steps 1–5, 9 partial.
2. `feat(jobs): persistent job queue with status lifecycle, remove quota` — steps 6–8, migration, 9 rest.
3. `feat(web,clients): task selector and per-task client endpoints` — steps 10–12, delete `task_loader.py`.

## Verification
- `pytest` green incl. new files.
- `PYTHONPATH=src uvicorn slacathon.main:app --reload`; `curl /tasks`; POST bad input → 422 body with `loc`; POST valid → `queued` + position; poll `/jobs/{id}`; `/leaderboard?task_id=fel` vs unfiltered; legacy `/validate` still works with `Deprecation` header.
- Start against copy of existing prod SQLite → migration rebuilds `jobs`, drops `quota_charges`, backfills leaderboard.
- `/board` shows selector, switches tasks.
- `kubectl kustomize kubernetes/overlays/{dev,prod}`.

## Risks
- `job_manager` import side-effect removal: tests importing it standalone must call `init_db()` first.
- Bounds on FEL/CUINJ EPICS extras is new 422 behaviour for existing clients; flag in PR.
- Queue is per-process; require uvicorn `workers=1` (check `scripts/` start script).
- `/submit` behind queue + FEL 30s timeout may exceed old client timeouts → 504 after `submit_timeout_seconds`, job still completes.
- Leaderboard `''` backfill is best guess from `settings.active_task`.
