# Task Development Guide

This guide explains how to add a new optimization challenge to the platform.

## Task Protocol

Every task module must implement the `Task` protocol defined in `app/tasks/base.py`:

```python
class Task(Protocol):
    Input: type[BaseModel]           # Pydantic model for submission inputs
    Result: type[BaseModel]          # Pydantic model for scored output
    TASK_NAME: str                   # Display name (shown in /task endpoint)
    INPUT_LABELS: list[str]          # Parameter names in order
    BOUNDS: list[tuple[float, float]] # (min, max) per parameter
    TARGET: float                    # Score that counts as "solved"
    MINIMIZE: bool                   # True = lower score is better
    FAILURE_SCORE: float             # Returned on evaluation error
    MAX_VALIDATIONS_PER_USER: int    # Per-user quota override
    def validate(self, data: BaseModel) -> BaseModel: ...
```

## Minimal Example

```python
# app/tasks/my_task.py
from pydantic import BaseModel
from app.tasks.base import TaskResult

TASK_NAME = "My Task"
INPUT_LABELS = ["x", "y"]
BOUNDS = [(-5.0, 5.0), (-5.0, 5.0)]
TARGET = 0.0
MINIMIZE = True
FAILURE_SCORE = 1.0e10
MAX_VALIDATIONS_PER_USER = 1000


class Input(BaseModel):
    x: float = 0.0
    y: float = 0.0
    model_config = {"extra": "forbid"}


class Result(TaskResult):
    pass


def validate(data: Input) -> Result:
    import time
    t0 = time.time()
    score = data.x ** 2 + data.y ** 2      # minimize x^2 + y^2
    solved = score < TARGET
    return Result(
        score=score,
        solved=solved,
        message=f"Score: {score:.6f}",
        evaltime=time.time() - t0,
    )
```

## Activating a Task

Set `SLACATHON_ACTIVE_TASK` to the module filename (without `.py`):

```bash
SLACATHON_ACTIVE_TASK=my_task uvicorn app.main:app --reload
```

Or in `.env`:
```
SLACATHON_ACTIVE_TASK=my_task
```

Restart the server. The task is loaded once at startup, validated, and cached.

## Validation

`task_loader.py` checks for all required attributes and raises a descriptive `RuntimeError` if any are missing. Check the startup logs if the server fails to start.

## Physics Data Files

If your task needs data files (e.g. particle distributions), place them in `app/tasks/` and reference them with a path relative to the module file:

```python
from pathlib import Path
DATA = Path(__file__).parent / "my_data_file.dat"
```

## Reference: Beamline Guru Task

The default task `app/tasks/flat_beam.py` implements the round-to-flat beam transform optimization. It uses a beam sigma matrix loaded from `app/tasks/fort.1` (IMPACT format) and 4×4 skew quadrupole + drift transport matrices. The objective function minimizes the x-y coupling in the output sigma matrix.

Key constants:
- 5 free parameters: `q1, q2, q3` (skew quad strengths), `d2, d3` (drift lengths)
- Solved when objective < 1e-4
- `MAX_VALIDATIONS_PER_USER = 10000`
