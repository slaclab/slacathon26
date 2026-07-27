import os
import time
import requests
from requests.adapters import HTTPAdapter

from .base import TaskInput, TaskResult


CUINJ_URL = os.getenv("CUINJ_URL", "https://ard-modeling-service.slac.stanford.edu/cuinj")

# Reuse one keep-alive connection pool across all validate() calls 
session = requests.Session()
session.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=20))

# All tunable inputs with the model's own ranges as bounds. The three is_constant
# inputs are omitted so the model fills them with its fixed defaults.
SELECTED = [
    ("CAMR:IN20:186:R_DIST", 210.21247820852545, 499.9996083265339),
    ("Pulse_length", 1.8181822778856414, 7.2718604921302035),
    ("SOLN:IN20:121:BACT", 0.3774080152672698, 0.4983800018349345),
    ("QUAD:IN20:121:BACT", -0.02098429469554406, 0.020999198106589838),
    ("QUAD:IN20:122:BACT", -0.020998830517503037, 0.020998929132148195),
    ("ACCL:IN20:300:L0A_PDES", -24.998714513984325, 9.991752397382681),
    ("ACCL:IN20:400:L0B_PDES", -24.99972566363747, 9.998904767155892),
    ("QUAD:IN20:361:BACT", -4.318053641915576, -1.0800430432494976),
    ("QUAD:IN20:371:BACT", 1.0913525514575348, 4.30967984810423),
    ("QUAD:IN20:425:BACT", -7.559759590824369, -1.080762695815712),
    ("QUAD:IN20:441:BACT", -1.0782202690353522, 7.559878303179915),
    ("QUAD:IN20:511:BACT", -1.0792451325247663, 7.5582919025608595),
    ("QUAD:IN20:525:BACT", -7.557932980106783, -1.0800286565992732),
]

class Input(TaskInput):
    model_config = {"extra": "allow"}


class Result(TaskResult):
    pass


TASK_NAME = "Injector Emittance"
INPUT_LABELS = [name for name, _, _ in SELECTED]
BOUNDS = [(lo, hi) for _, lo, hi in SELECTED]

# score = combined norm. emittance (um), lower is better; no fixed solved threshold
TARGET = 0.0
MINIMIZE = True
FAILURE_SCORE = 1.0e10
MAX_VALIDATIONS_PER_USER = 10000


def validate(data: Input) -> Result:
    if not isinstance(data, Input):
        data = Input(**data)

    inputs = data.model_dump()

    time0 = time.time()
    try:
        resp = session.post(f"{CUINJ_URL}/predict", json={"inputs": inputs}, timeout=30)
        resp.raise_for_status()
        out = resp.json()["outputs"]
        # Combined transverse emittance (geometric mean of the two planes), in um.
        emit = 1.0e6 * (float(out["norm_emit_x"]) * float(out["norm_emit_y"])) ** 0.5
    except Exception as e:
        dt = float(time.time() - time0)
        return Result(solved=False, score=1.0e10, message=f"Injector service error: {e}", evaltime=dt)
    dt = float(time.time() - time0)

    return Result(
        solved=False,
        score=emit,
        message=f"combined norm. emittance is {emit} um (lower is better)",
        evaltime=dt
    )