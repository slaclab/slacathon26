"""
Task registry: every module in slacathon.tasks is loaded at startup and served side by side.

A task module exposes `TASK = XxxProblem()` (see tasks/base.py); legacy module-style tasks
are wrapped by ModuleProblem. Each task has a public alias (`public_task_id`: PUBLIC_ID or module
name, e.g. "flat_beam", "fel") used in URLs, and an internal `task_id` derived from it and stored
in the `tasks` table at launch; jobs and leaderboard rows reference the internal id.
"""

import importlib
import logging
import pkgutil
from types import ModuleType

from . import db as _db
from . import tasks as _tasks_pkg
from .tasks.base import Problem, resolve_problem

logger = logging.getLogger(__name__)

_SKIP = {"base"}

_registry: dict[str, Problem] | None = None   # keyed by public_task_id
_by_id: dict[str, Problem] = {}               # keyed by internal task_id


def discover_tasks(package: ModuleType = _tasks_pkg) -> dict[str, Problem]:
    """Import every task module in `package` (skipping base, _private and subpackages); keyed by public_task_id."""
    found: dict[str, Problem] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if info.ispkg or info.name in _SKIP or info.name.startswith("_"):
            continue
        name = f"{package.__name__}.{info.name}"
        try:
            module = importlib.import_module(name)
        except Exception as e:
            raise RuntimeError(f"Could not load task '{name}': {e}") from e
        problem = resolve_problem(module)
        if problem.public_task_id in found:
            raise RuntimeError(f"Duplicate public task id '{problem.public_task_id}' in '{name}'")
        found[problem.public_task_id] = problem
        logger.info(f"Registered task '{problem.public_task_id}' ({problem.task_id}): {problem.TASK_NAME}")
    if not found:
        raise RuntimeError(f"No tasks found in '{package.__name__}'")
    return found


def get_registry() -> dict[str, Problem]:
    """Load (once) all tasks, persist them in the tasks table, and return them keyed by public_task_id."""
    global _registry
    if _registry is None:
        registry = discover_tasks()
        _db.init_db()
        _db.sync_tasks([(p.task_id, p.public_task_id, p.TASK_NAME) for p in registry.values()])
        _by_id.update({p.task_id: p for p in registry.values()})
        _registry = registry
    return _registry


def get_task(public_task_id: str) -> Problem:
    """Return the task for its public alias; raises KeyError if unknown."""
    return get_registry()[public_task_id]


def get_task_by_id(task_id: str) -> Problem | None:
    """Return the task for its internal id, or None."""
    get_registry()
    return _by_id.get(task_id)


def list_tasks() -> list[Problem]:
    return list(get_registry().values())
