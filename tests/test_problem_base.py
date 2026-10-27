"""Problem base class: input checking, metadata, legacy module adapter."""
import types

import pytest

from slacathon.tasks import cuinj, fel, flat_beam
from slacathon.tasks.base import (
    InputValidationError,
    ModuleProblem,
    Problem,
    TaskInput,
    TaskResult,
    make_task_id,
    resolve_problem,
)


@pytest.mark.parametrize("module", [flat_beam, fel, cuinj])
def test_task_modules_expose_problem(module):
    problem = resolve_problem(module)
    assert isinstance(problem, Problem)
    assert problem is module.TASK
    assert problem.public_task_id == module.__name__.rsplit(".", 1)[-1]
    assert problem.task_id == make_task_id(problem.public_task_id)
    meta = problem.metadata()
    assert meta["name"] == module.TASK_NAME
    assert meta["bounds"] == module.BOUNDS
    assert {"public_task_id", "input_schema", "result_schema", "max_concurrency"} <= meta.keys()


def test_check_input_ok():
    data = flat_beam.TASK.check_input({"q1": 1.0, "q2": 0, "q3": 0, "d2": 0, "d3": 0})
    assert isinstance(data, flat_beam.Input)


def test_check_input_unknown_field():
    with pytest.raises(InputValidationError) as exc:
        flat_beam.TASK.check_input({"q9": 1.0})
    assert exc.value.errors[0]["loc"] == ["input", "q9"]


def test_check_input_out_of_bounds():
    with pytest.raises(InputValidationError) as exc:
        flat_beam.TASK.check_input({"q1": 11.0})
    assert exc.value.errors == [
        {"loc": ["input", "q1"], "msg": "Value 11.0 outside bounds [-10.0, 10.0]", "type": "value_error.bounds"}
    ]


def test_check_input_not_a_dict():
    with pytest.raises(InputValidationError) as exc:
        flat_beam.TASK.check_input([1, 2, 3])
    assert exc.value.errors[0]["loc"] == ["input"]


def test_check_input_extra_allow_bounds():
    label, (lo, hi) = fel.INPUT_LABELS[0], fel.BOUNDS[0]
    assert fel.TASK.check_input({}) is not None  # missing knobs: model defaults
    fel.TASK.check_input({label: (lo + hi) / 2})
    with pytest.raises(InputValidationError) as exc:
        fel.TASK.check_input({label: hi + 1.0})
    assert exc.value.errors[0]["type"] == "value_error.bounds"


def test_validate_compat_accepts_dict():
    res = flat_beam.TASK.validate({"q1": 0, "q2": 0, "q3": 0, "d2": 0, "d3": 0})
    assert isinstance(res, flat_beam.Result)


def test_failure_result():
    assert flat_beam.TASK.failure_result("boom") == {
        "solved": False, "score": 1.0e10, "message": "boom", "evaltime": 0.0,
    }


def test_module_problem_wraps_legacy_module():
    module = types.ModuleType("slacathon.tasks.legacy")
    module.Input = TaskInput
    module.Result = TaskResult
    module.TASK_NAME = "Legacy"
    module.INPUT_LABELS = []
    module.BOUNDS = []
    module.TARGET = 1.0
    module.validate = lambda data: TaskResult(score=2.0, solved=False, message="ok", evaltime=0.0)

    problem = resolve_problem(module)
    assert isinstance(problem, ModuleProblem)
    assert problem.public_task_id == "legacy"
    assert problem.TARGET == 1.0
    assert problem.validate({}).score == 2.0


def test_resolve_problem_rejects_invalid_module():
    with pytest.raises(RuntimeError):
        resolve_problem(types.ModuleType("slacathon.tasks.empty"))


def test_public_id_override():
    module = types.ModuleType("slacathon.tasks.some_file")
    class P(Problem):
        PUBLIC_ID = "alias"
        def run(self, data):
            return TaskResult(score=0.0, solved=True, message="", evaltime=0.0)
    module.TASK = P()
    problem = resolve_problem(module)
    assert problem.public_task_id == "alias"
    assert problem.task_id == make_task_id("alias")
