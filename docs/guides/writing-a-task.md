# Writing a Task

Tasks are Python modules in `src/slacathon/tasks/`. The active task is selected by `SLACATHON_ACTIVE_TASK` at startup.

## Task Protocol

A task module must expose these module-level names (defined in `tasks/base.py`):

```python
from pydantic import BaseModel

class Input(BaseModel):
    # Define your input parameters here
    x: float = 0.0
    model_config = {"extra": "forbid"}   # recommended

class Result(BaseModel):
    score: float
    solved: bool
    message: str
    evaltime: float

def validate(data: Input) -> Result:
    # Compute and return score
    ...

TASK_NAME: str                  # display name
INPUT_LABELS: list[str]         # one label per Input field, same order
BOUNDS: list[tuple[float, float]]  # (min, max) per parameter
TARGET: float                   # score at which the problem is considered solved
MINIMIZE: bool                  # True = lower score is better
FAILURE_SCORE: float            # returned on error (default 1e10)
MAX_VALIDATIONS_PER_USER: int   # per-user quota override
```

## Minimal Example

```python
# src/slacathon/tasks/my_task.py
import time
from .base import TaskInput, TaskResult

class Input(TaskInput):
    x: float = 0.0
    y: float = 0.0
    model_config = {"extra": "forbid"}

class Result(TaskResult):
    pass

def validate(data: Input) -> Result:
    t0 = time.time()
    score = (data.x ** 2) + (data.y ** 2)   # minimize toward 0
    return Result(
        score=score,
        solved=score < 1e-4,
        message=f"f(x,y) = {score:.6f}",
        evaltime=time.time() - t0
    )

TASK_NAME = "My Task"
INPUT_LABELS = ["x", "y"]
BOUNDS = [(-5.0, 5.0), (-5.0, 5.0)]
TARGET = 0.0
MINIMIZE = True
FAILURE_SCORE = 1.0e10
MAX_VALIDATIONS_PER_USER = 10000
```

Activate it:

```bash
SLACATHON_ACTIVE_TASK=my_task PYTHONPATH=src uvicorn slacathon.main:app --reload
```

Verify:

```bash
curl http://localhost:8000/slacathon26/task
```

## External Service Tasks

`fel` and `cuinj` call the SLAC ARD modeling service via `requests`. Key patterns:

- Use a module-level `requests.Session` with connection pooling (`HTTPAdapter`).
- Handle `Exception` broadly and return `Result(score=FAILURE_SCORE, ...)` on service errors — the API call must not fail with HTTP 500.
- Accept an environment variable override for the service URL (e.g. `FEL_URL = os.getenv("FEL_URL", "...")`).
- `validate()` runs in a thread pool (`run_in_executor`), so it can be synchronous and blocking.

## Score Direction

- `MINIMIZE = True` → lower score is better. Leaderboard sorts ascending.
- `MINIMIZE = False` → higher score is better. Leaderboard sorts descending.

`TARGET` is the threshold for `solved=True`. For `MINIMIZE=True`, `solved = score <= TARGET`. Check your task's `validate()` for the exact condition.

## Input Schema

`Input` is a Pydantic model. `GET /task` returns its JSON schema. Client libraries use this to discover parameter names and bounds dynamically.

Use `model_config = {"extra": "forbid"}` for strict tasks (unknown fields rejected) or `{"extra": "allow"}` for tasks where the model service may consume extra inputs (e.g. `fel`).
