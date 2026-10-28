# Writing a Task

Tasks are Python modules in `src/slacathon/tasks/`. Every module there (except `base` and `_private` ones) is discovered at startup by `registry.py` and served side by side. Its public alias `public_task_id` (used in URLs and the dashboard) is `PUBLIC_ID` if set, else the module name (e.g. `flat_beam`, `fel`, `cuinj`). The internal `task_id` is derived from the alias (`uuid5`, see `make_task_id`) and stored in the `tasks` table at launch; jobs and leaderboard rows use it. Keep the alias stable (set `PUBLIC_ID` before renaming a module) or history will be orphaned.

## Problem class

A task module exposes `TASK`, an instance of a `Problem` subclass (`tasks/base.py`):

```python
from slacathon.tasks.base import Problem, TaskInput, TaskResult

class Input(TaskInput):
    x: float = 0.0
    y: float = 0.0
    model_config = {"extra": "forbid"}   # recommended

class Result(TaskResult):
    pass

class MyProblem(Problem):
    PUBLIC_ID = "my_task"    # optional; defaults to module name
    TASK_NAME = "My Task"
    INPUT_LABELS = ["x", "y"]
    BOUNDS = [(-5.0, 5.0), (-5.0, 5.0)]
    TARGET = 0.0
    MINIMIZE = True          # default
    FAILURE_SCORE = 1.0e10   # default
    MAX_CONCURRENCY = 1      # default; raise for I/O-bound tasks
    Input = Input
    Result = Result

    def run(self, data: Input) -> Result:
        ...

TASK = MyProblem()
```

`Problem.check_input()` validates the schema and `BOUNDS` before `run()` is called; failures return HTTP 422 from `POST /tasks/{public_task_id}/submit`. Legacy modules with module-level constants and a `validate()` function are still accepted (wrapped by `ModuleProblem`).

Run the server (all tasks load) and verify:

```bash
PYTHONPATH=src uvicorn slacathon.main:app --reload
curl http://localhost:8000/slacathon26/tasks
curl http://localhost:8000/slacathon26/tasks/my_task
```

## External Service Tasks

`fel` and `cuinj` call the SLAC ARD modeling service via `requests`. Key patterns:

- Use a module-level `requests.Session` with connection pooling (`HTTPAdapter`).
- Handle `Exception` broadly and return `Result(score=FAILURE_SCORE, ...)` on service errors — the API call must not fail with HTTP 500.
- Accept an environment variable override for the service URL (e.g. `FEL_URL = os.getenv("FEL_URL", "...")`).
- `run()` runs in a thread pool (`run_in_executor`), so it can be synchronous and blocking.

## Score Direction

- `MINIMIZE = True` → lower score is better. Leaderboard sorts ascending.
- `MINIMIZE = False` → higher score is better. Leaderboard sorts descending.

`TARGET` is the threshold for `solved=True`. For `MINIMIZE=True`, `solved = score <= TARGET`. Check your task's `run()` for the exact condition.

## Input Schema

`Input` is a Pydantic model. `GET /tasks/{public_task_id}` returns its JSON schema. Client libraries use this to discover parameter names and bounds dynamically.

Use `model_config = {"extra": "forbid"}` for strict tasks (unknown fields rejected) or `{"extra": "allow"}` for tasks where the model service may consume extra inputs (e.g. `fel`).
