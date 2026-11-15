# Proposed GitHub Issues — Run-scoped Validation & Submission (PLAT-1..5)

Terminology: a **task** is a problem (one class in `src/slacathon/tasks/`).

Agreed flow: a team **opens a run** on a task and receives a `run_id`, then calls
`POST /validate` with API key + `run_id` + task parameters. Each run has a maximum
number of validations, set by the application configuration
(`SLACATHON_MAX_VALIDATIONS_PER_RUN`), same default for all tasks.

**Authentication:** every endpoint in these issues requires the API key
(`verify_api_key`). Missing or invalid key → `401`.
When satisfied, the team calls `POST /submit` with the `run_id` to place a
re-evaluated setting on the leaderboard.

---

## Issue 0 — Epic: Run-scoped validation and submission (PLAT-1..5)

**Labels:** `epic`, `api`

Track implementation of platform requirements PLAT-1..PLAT-5.

- [ ] #1 Run creation API (PLAT-2)
- [ ] #2 `/validate` requires `run_id`, never touches leaderboard (PLAT-1, PLAT-2)
- [ ] #3 `/submit` linked to a run (PLAT-1, PLAT-2)
- [ ] #4 Out-of-range inputs rejected with 422, not charged (PLAT-3)
- [ ] #5 `GET /task` exposes ranges, model version, threshold, remaining quota (PLAT-4)
- [ ] #6 No charge on platform/model errors (PLAT-5)
- [ ] #7 Test coverage for runs and quota rules

---

## Issue 1 — feat(api): add run creation for a task (PLAT-2)

**Labels:** `enhancement`, `api`, `db`

### Description
A team must open a run on a task before validating. The run groups
evaluations so a submission can report how many evaluations its run used.

### API
- `POST /tasks/{task_name}/runs`
  - optional body `{ "label": "<team chosen name>" }`
  - response `201 { "run_id", "task", "max_validations", "validations_used": 0, "created_at" }`
  - `404` unknown task
- `GET /runs/{run_id}` → `{ run_id, task, max_validations, validations_used, remaining, created_at }`
  - `403` if run belongs to another user, `404` if missing
- `GET /runs` → list of the caller's runs (optional `?task=`)

### Acceptance criteria
- [ ] `run_id` is server-generated (UUID), bound to user + task.
- [ ] Max validations per run read from application setting
      `SLACATHON_MAX_VALIDATIONS_PER_RUN` (global default for all tasks).
- [ ] Limit is copied into the run at creation, so config changes do not affect open runs.
- [ ] Run state persisted (survives restart).

### Implementation notes
- `src/slacathon/db.py`: new table
  `runs(run_id TEXT PK, user_id, task_name, label, max_validations, validations_used INT DEFAULT 0, created_at)`
  + helpers `create_run`, `get_run`, `list_runs`, `try_consume_run_validation` (atomic
  `UPDATE runs SET validations_used = validations_used + 1 WHERE run_id=? AND validations_used < max_validations`),
  `release_run_validation`.
- `src/slacathon/settings.py`: add `max_validations_per_run: int` (env `SLACATHON_MAX_VALIDATIONS_PER_RUN`).
- Resolve task via `task_loader.py` registry.

---

## Issue 2 — feat(api): `/validate` requires `run_id` and never touches leaderboard (PLAT-1, PLAT-2)

**Labels:** `enhancement`, `api`

### Description
`/validate` evaluates a setting within a run and returns the score. It must
never write to the leaderboard.

### Request
`POST /validate` `{ "run_id": "...", "input": { ...task parameters... } }`

### Acceptance criteria
- [ ] Missing `run_id` → `422`.
- [ ] Unknown run → `404`; run owned by another user → `403`.
- [ ] Task resolved from the run (no separate task param needed).
- [ ] Run validation limit reached → `429` with `{ max_validations, validations_used }`.
- [ ] Response includes `job_id`, `run_id`, `validations_used`, `remaining`.
- [ ] `GET /jobs/{job_id}` result includes `run_id`.
- [ ] No leaderboard writes on this path (test asserts).

### Implementation notes
- `src/slacathon/main.py` `validate()` (~L346): consume run slot atomically,
  store `run_id` on job (`jobs` table column), dispatch to the run's task.

---

## Issue 3 — feat(api): `/submit` places a re-evaluated setting linked to a run (PLAT-1, PLAT-2)

**Labels:** `enhancement`, `api`, `leaderboard`

### Description
`/submit` re-evaluates the setting server-side and places it on the leaderboard,
reporting the number of evaluations its run used.

### Request
`POST /submit` `{ "run_id": "...", "input": { ... } }`

### Acceptance criteria
- [ ] Run ownership checked (`403`/`404`).
- [ ] Setting re-evaluated server-side; client score never trusted.
- [ ] Leaderboard entry stores `run_id` and `evaluations_used` (= run's `validations_used` at submit time).
- [ ] `/leaderboard` exposes `evaluations_used` per entry.
- [ ] Submission does not consume a run validation slot.

### Implementation notes
- `db.py`: add `run_id`, `evaluations_used` columns to `leaderboard` (migration for existing DB).
- `main.py` `submit_result()` (~L278).

---

## Issue 4 — fix(api): reject out-of-range inputs with 422 without charging quota (PLAT-3)

**Labels:** `bug`, `api`, `quota`

### Description
Today invalid input can fall into the generic `except` and return `500`, and on
`/submit` quota is charged before input validation.

### Acceptance criteria
- [ ] Input validated against pydantic schema + task `BOUNDS` before any charge.
- [ ] Response `422` with per-field errors (name, value, allowed range).
- [ ] No quota charge and no run slot consumed (tests assert counts unchanged).
- [ ] Applies to both `/validate` and `/submit`.

---

## Issue 5 — feat(api): `GET /task` exposes ranges, model version, solved threshold, remaining quota (PLAT-4)

**Labels:** `enhancement`, `api`

### Acceptance criteria
- [ ] Response (per task, e.g. `GET /tasks/{task_name}`) includes: `bounds`,
      `model_version`, `solved_threshold`, `max_validations_per_run`.
- [ ] API key required (`401` without it).
- [ ] Includes caller's `remaining_quota` (global user quota) and open runs summary.

### Implementation notes
- Add `MODEL_VERSION` and `SOLVED_THRESHOLD` (or map existing `TARGET`) to task classes.
- Add `Depends(verify_api_key)` to `get_task_info()` (currently public).

---

## Issue 6 — fix(api): do not charge quota on platform or model service errors (PLAT-5)

**Labels:** `bug`, `quota`, `reliability`

### Description
Charges happen before evaluation (`charge_validation_quota`, `job_manager.py`)
and failed background jobs currently store a fake `FAILURE_SCORE` result.

### Acceptance criteria
- [ ] On evaluation exception / model service error: quota charge refunded and run slot released.
- [ ] Job status becomes `failed` with error message (no fake score).
- [ ] `/submit` platform error → `5xx`/`503`, no charge.
- [ ] User errors (422) and successful evaluations behave as before.

### Implementation notes
- Reserve-then-commit: reserve on enqueue, commit on success, release on failure
  (`run_validation_job` in `main.py`, `charge_quota` in `db.py`).

---

## Issue 7 — test: coverage for runs and quota rules

**Labels:** `test`

- [ ] `tests/test_runs.py`: create/get/list runs, foreign run 403, limit 429.
- [ ] `/validate` never writes leaderboard; `/submit` stores `evaluations_used`.
- [ ] Out-of-range → 422, counts unchanged.
- [ ] Simulated task exception → no charge, job `failed`.
- [ ] `/task` returns all fields with API key; `401` without.
- [ ] Every run/validate/submit/task endpoint returns `401` without API key.

---

## Open questions
0. Later: allow per-task override of the max validations per run?
1. Do runs expire or can a team close a run explicitly?
2. Is `/submit` allowed when the run has exhausted its validations? (proposed: yes)
3. Can a run be submitted more than once? (proposed: yes, latest/best kept per leaderboard rules)
4. Does the global per-user quota still apply on top of the per-run limit? (proposed: yes)
