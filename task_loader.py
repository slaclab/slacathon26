"""
Active task loaded via ACTIVE_TASK env (default "beamline").

Task modules must provide: Input, Result, TASK_NAME, INPUT_LABELS, BOUNDS, validate.
See tasks/base.py .
"""

import os
import importlib
from types import ModuleType


def load_active_task() -> ModuleType:
    task_name = os.getenv("ACTIVE_TASK", "beamline").strip().lower()
    try:
        module = importlib.import_module(f"tasks.{task_name}")
    except ImportError as e:
        raise RuntimeError(
            f"Could not load task 'tasks.{task_name}'. "
            f"Ensure tasks/{task_name}.py exists. Error: {e}"
        )

    required = ["Input", "Result", "TASK_NAME", "validate"]
    for attr in required:
        if not hasattr(module, attr):
            raise RuntimeError(
                f"Task 'tasks.{task_name}' missing required '{attr}'. "
                "See tasks/base.py for the expected interface."
            )

    return module
