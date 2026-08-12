import os
import time
import requests
from requests.adapters import HTTPAdapter

from .base import TaskInput, TaskResult


FEL_URL = os.getenv("FEL_URL", "https://ard-modeling-service.slac.stanford.edu/fel")

# Reuse one keep-alive connection pool across all validate() calls so we skip
# the TLS handshake on every prediction (validate runs in a thread pool).
session = requests.Session()
session.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=20))

# Tuned knobs: highest-sensitivity quadrupoles plus the solenoid
# Can adjust as needed
SELECTED = [
    ("QUAD:LI29:401:BCTRL", 11.776640892028809, 14.72998332977295),
    ("QUAD:LI25:901:BCTRL", -8.701128005981445, -5.903156280517578),
    ("QUAD:LI22:601:BCTRL", 3.7713868618011475, 6.909282684326172),
    ("QUAD:LI24:601:BCTRL", 6.159085750579834, 9.750685691833496),
    ("QUAD:LI27:701:BCTRL", -12.907695770263672, -9.589673042297363),
    ("QUAD:LI27:501:BCTRL", -12.33036994934082, -9.249858856201172),
    ("QUAD:IN20:771:BCTRL", -3.473116636276245, -3.41040301322937),
    ("QUAD:LI30:401:BCTRL", 13.69515609741211, 15.213142395019531),
    ("QUAD:LI27:801:BCTRL", 9.860147476196289, 13.635490417480469),
    ("QUAD:LI23:801:BCTRL", 5.585941314697266, 10.347235679626465),
    ("SOLN:IN20:311:BCTRL", -0.0006276898202486336, -0.000619793776422739),
]

class Input(TaskInput):
    model_config = {"extra": "allow"}


class Result(TaskResult):
    pass


TASK_NAME = "FEL Pulse Intensity"
INPUT_LABELS = [name for name, _, _ in SELECTED]
BOUNDS = [(lo, hi) for _, lo, hi in SELECTED]

# score = -intensity, so minimizing score maximizes intensity; solved at 4 mJ -> score -4.0
TARGET = -4.0
MINIMIZE = True
FAILURE_SCORE = 1.0e10
MAX_VALIDATIONS_PER_USER = 10000


def validate(data: Input) -> Result:
    if not isinstance(data, Input):
        data = Input(**data)

    # Only the tuned knobs are sent. The model fills its own defaults for the rest.
    inputs = data.model_dump()

    time0 = time.time()
    try:
        resp = session.post(f"{FEL_URL}/predict", json={"inputs": inputs}, timeout=30)
        resp.raise_for_status()
        intensity = float(resp.json()["outputs"]["hxr_pulse_intensity"])
    except Exception as e:
        dt = float(time.time() - time0)
        return Result(solved=False, score=1.0e10, message=f"FEL service error: {e}", evaltime=dt)
    dt = float(time.time() - time0)

    # Platform minimizes score, so take -intensity
    return Result(
        solved=intensity >= 4.0,
        score=-intensity,
        message=f"hxr_pulse_intensity is {intensity} mJ (solved at 4 mJ)",
        evaltime=dt
    )