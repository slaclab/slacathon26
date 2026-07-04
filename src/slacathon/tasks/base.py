from pydantic import BaseModel
from typing import Protocol, runtime_checkable

class TaskInput(BaseModel):
    pass

class TaskResult(BaseModel):
    score: float
    solved: bool
    message: str
    evaltime: float

@runtime_checkable
class Task(Protocol):
    Input: type[BaseModel]
    Result: type[BaseModel]
    TASK_NAME: str
    INPUT_LABELS: list[str]
    BOUNDS: list[tuple[float, float]]
    TARGET: float
    MINIMIZE: bool
    FAILURE_SCORE: float
    MAX_VALIDATIONS_PER_USER: int

    def validate(self, data: BaseModel) -> BaseModel:
        ...
