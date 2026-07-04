"""
Active task loaded via SLACATHON_ACTIVE_TASK (settings / env / .env, default "flat_beam").

Task modules must provide: Input, Result, TASK_NAME, INPUT_LABELS, BOUNDS, TARGET, MINIMIZE,
FAILURE_SCORE, MAX_VALIDATIONS_PER_USER, validate.
See tasks/base.py .
"""

from .settings import settings
import importlib
from types import ModuleType

_loaded_task: ModuleType | None = None


def load_active_task() -> ModuleType:
    """Load (and cache) the active task module exactly once to avoid duplicate heavy init (e.g. fort.1)."""
    global _loaded_task
    if _loaded_task is not None:
        return _loaded_task
    task_name = settings.active_task.strip().lower()
    try:
        module = importlib.import_module(f"slacathon.tasks.{task_name}")
    except ImportError as e:
        raise RuntimeError(
            f"Could not load task 'slacathon.tasks.{task_name}'. "
            f"Ensure src/slacathon/tasks/{task_name}.py exists. Error: {e}"
        )

    required = ["Input", "Result", "TASK_NAME", "INPUT_LABELS", "BOUNDS", "TARGET", "MINIMIZE", "FAILURE_SCORE", "MAX_VALIDATIONS_PER_USER", "validate"]
    for attr in required:
        if not hasattr(module, attr):
            raise RuntimeError(
                f"Task 'slacathon.tasks.{task_name}' missing required '{attr}'. "
                "See slacathon/tasks/base.py for the expected interface."
            )

    _loaded_task = module
    # Apply task MAX to job_manager so direct use of core (without main) sees the task value
    try:
        from . import job_manager
        if hasattr(module, "MAX_VALIDATIONS_PER_USER"):
            job_manager.set_max_validations_per_user(getattr(module, "MAX_VALIDATIONS_PER_USER"))
    except Exception:
        pass
    return module
