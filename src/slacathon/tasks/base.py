import uuid
from abc import ABC, abstractmethod
from types import ModuleType
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError


class TaskInput(BaseModel):
    pass


class TaskResult(BaseModel):
    score: float
    solved: bool
    message: str
    evaltime: float


class InputValidationError(ValueError):
    """Raised by Problem.check_input; errors are pydantic-like dicts {loc, msg, type}."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in errors))


@runtime_checkable
class TaskModule(Protocol):
    """Legacy module-style task: constants + module-level validate()."""

    Input: type[BaseModel]
    Result: type[BaseModel]
    TASK_NAME: str
    INPUT_LABELS: list[str]
    BOUNDS: list[tuple[float, float]]
    TARGET: float

    def validate(self, data: BaseModel) -> BaseModel:
        ...


# Backwards-compatible name
Task = TaskModule

# Namespace for deterministic internal task ids (uuid5 over the public alias)
TASK_ID_NAMESPACE = uuid.UUID("6f1c2d6e-5a3b-4c8e-9a51-2b7d0e4f8c10")


def make_task_id(public_task_id: str) -> str:
    """Internal task id: stable UUID derived from the public alias, no configuration needed."""
    return str(uuid.uuid5(TASK_ID_NAMESPACE, public_task_id))


class Problem(ABC):
    """Canonical task abstraction. Task modules expose `TASK = XxxProblem()`.

    public_task_id: human-readable alias used in URLs/dashboard (PUBLIC_ID, else module name).
    task_id: internal id derived from the alias (make_task_id); used by jobs and leaderboard rows.
    """

    PUBLIC_ID: str = ""
    public_task_id: str = ""
    task_id: str = ""
    TASK_NAME: str = ""
    INPUT_LABELS: list[str] = []
    BOUNDS: list[tuple[float, float]] = []
    TARGET: float = 0.0
    MINIMIZE: bool = True
    FAILURE_SCORE: float = 1.0e10
    MAX_CONCURRENCY: int = 1
    # Deprecated: kept until per-user quota is removed
    MAX_VALIDATIONS_PER_USER: int | None = None
    Input: type[TaskInput] = TaskInput
    Result: type[TaskResult] = TaskResult

    def check_input(self, raw: Any) -> TaskInput:
        """Parse and bounds-check raw input; raise InputValidationError on any problem."""
        if isinstance(raw, self.Input):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            raise InputValidationError([{"loc": ["input"], "msg": "Input must be an object", "type": "type_error.dict"}])
        try:
            data = self.Input.model_validate(raw)
        except ValidationError as e:
            raise InputValidationError([
                {"loc": ["input", *e_["loc"]], "msg": e_["msg"], "type": e_["type"]} for e_ in e.errors()
            ])

        extra = data.model_extra or {}
        errors = []
        for label, (lo, hi) in zip(self.INPUT_LABELS, self.BOUNDS):
            value = extra[label] if label in extra else getattr(data, label, None)
            if value is None:
                continue  # missing knob: model fills its own default
            try:
                value = float(value)
            except (TypeError, ValueError):
                errors.append({"loc": ["input", label], "msg": "Value must be a number", "type": "type_error.float"})
                continue
            if not (lo <= value <= hi):
                errors.append({
                    "loc": ["input", label],
                    "msg": f"Value {value} outside bounds [{lo}, {hi}]",
                    "type": "value_error.bounds",
                })
        if errors:
            raise InputValidationError(errors)
        return data

    @abstractmethod
    def run(self, data: TaskInput) -> TaskResult:
        ...

    def validate(self, data: Any) -> TaskResult:
        """Compat with legacy module-level validate(): accepts dict or Input."""
        if not isinstance(data, self.Input):
            data = self.Input(**data)
        return self.run(data)

    def metadata(self) -> dict:
        return {
            "public_task_id": self.public_task_id,
            "name": self.TASK_NAME,
            "input_schema": self.Input.model_json_schema(),
            "result_schema": self.Result.model_json_schema(),
            "parameter_labels": self.INPUT_LABELS,
            "bounds": self.BOUNDS,
            "target": self.TARGET,
            "minimize": self.MINIMIZE,
            "failure_score": self.FAILURE_SCORE,
            "max_concurrency": self.MAX_CONCURRENCY,
            "max_validations_per_user": self.MAX_VALIDATIONS_PER_USER,
        }

    def failure_result(self, message: str) -> dict:
        return {"solved": False, "score": self.FAILURE_SCORE, "message": message, "evaltime": 0.0}


class ModuleProblem(Problem):
    """Adapter wrapping a legacy module-style task (see TaskModule)."""

    def __init__(self, module: ModuleType):
        self._module = module
        for attr in ("PUBLIC_ID", "Input", "Result", "TASK_NAME", "INPUT_LABELS", "BOUNDS", "TARGET",
                     "MINIMIZE", "FAILURE_SCORE", "MAX_CONCURRENCY", "MAX_VALIDATIONS_PER_USER"):
            if hasattr(module, attr):
                setattr(self, attr, getattr(module, attr))

    def run(self, data: TaskInput) -> TaskResult:
        return self._module.validate(data)


def resolve_problem(module: ModuleType) -> Problem:
    """Return the module's Problem (TASK instance, or legacy-module adapter) with ids assigned."""
    problem = getattr(module, "TASK", None)
    if not isinstance(problem, Problem):
        if not isinstance(module, TaskModule):
            raise RuntimeError(
                f"Task '{module.__name__}' exposes neither TASK (Problem instance) nor the legacy "
                "module interface. See slacathon/tasks/base.py."
            )
        problem = ModuleProblem(module)
    problem.public_task_id = problem.PUBLIC_ID or module.__name__.rsplit(".", 1)[-1]
    problem.task_id = make_task_id(problem.public_task_id)
    return problem

