import numpy as np
import time
from pydantic import BaseModel

from .base import TaskInput, TaskResult

try:
    import importlib.resources as pkg_resources
except ImportError:
    import importlib_resources as pkg_resources  # backport for older py


class Input(TaskInput):
    q1: float = 0.0
    q2: float = 0.0
    q3: float = 0.0
    d2: float = 0.0
    d3: float = 0.0

    model_config = {"extra": "forbid"}


class Result(TaskResult):
    pass


def readsigma4(fname):
    disti = np.loadtxt(fname)
    dist = disti.copy()

    # convert from impact format
    dist[:, 1] = disti[:, 1] / disti[:, 5]
    dist[:, 3] = disti[:, 3] / disti[:, 5]

    # calculate beam second moments
    sigma4 = np.zeros((4, 4))
    for i in range(4):
        for j in range(4):
            sigma4[i, j] = np.mean(dist[:, i] * dist[:, j])

    return sigma4


L = 0.15
# Load fort.1 via importlib.resources so it works whether installed or run from src/
fort1_path = pkg_resources.files("slacathon.tasks.data") / "fort.1"
fname = str(fort1_path)
sigma4 = readsigma4(fname)


def Rotate(phi):
    R = [[np.cos(phi), 0, np.sin(phi), 0], 
         [0, np.cos(phi), 0, np.sin(phi)], 
         [-np.sin(phi), 0, np.cos(phi), 0], 
         [0, -np.sin(phi), 0, np.cos(phi)]]
    return np.asarray(R)


def QskewFD(q, L):  # First magnet focusing in xx', defocusing in yy'
    Kappa = q / L
    Qs11 = np.cos(L * np.sqrt(Kappa))
    Qs12 = np.sin(L * np.sqrt(Kappa)) / np.sqrt(Kappa)
    Qs13 = 0
    Qs14 = 0
    Qs21 = -np.sqrt(Kappa) * np.sin(L * np.sqrt(Kappa))
    Qs22 = np.cos(L * np.sqrt(Kappa))
    Qs23 = 0
    Qs24 = 0
    Qs31 = 0
    Qs32 = 0
    Qs33 = np.cosh(L * np.sqrt(Kappa))
    Qs34 = np.sinh(L * np.sqrt(Kappa)) / np.sqrt(Kappa)
    Qs41 = 0
    Qs42 = 0
    Qs43 = np.sqrt(Kappa) * np.sinh(L * np.sqrt(Kappa))
    Qs44 = np.cosh(L * np.sqrt(Kappa))
    Qs = [[Qs11, Qs12, Qs13, Qs14], 
          [Qs21, Qs22, Qs23, Qs24], 
          [Qs31, Qs32, Qs33, Qs34], 
          [Qs41, Qs42, Qs43, Qs44]]
    Qskew = Rotate(-np.pi / 4.0).dot(np.asarray(Qs)).dot(Rotate(np.pi / 4.0))
    return np.asarray(Qskew)


def QskewDF(q, L):  # First magnet focusing in yy', defocusing in xx'
    Kappa = q / L
    Qs11 = np.cosh(L * np.sqrt(Kappa))
    Qs12 = np.sinh(L * np.sqrt(Kappa)) / np.sqrt(Kappa)
    Qs13 = 0
    Qs14 = 0
    Qs21 = np.sqrt(Kappa) * np.sinh(L * np.sqrt(Kappa))
    Qs22 = np.cosh(L * np.sqrt(Kappa))
    Qs23 = 0
    Qs24 = 0
    Qs31 = 0
    Qs32 = 0
    Qs33 = np.cos(L * np.sqrt(Kappa))
    Qs34 = np.sin(L * np.sqrt(Kappa)) / np.sqrt(Kappa)
    Qs41 = 0
    Qs42 = 0
    Qs43 = -np.sqrt(Kappa) * np.sin(L * np.sqrt(Kappa))
    Qs44 = np.cos(L * np.sqrt(Kappa))
    Qs = [[Qs11, Qs12, Qs13, Qs14], 
          [Qs21, Qs22, Qs23, Qs24], 
          [Qs31, Qs32, Qs33, Qs34], 
          [Qs41, Qs42, Qs43, Qs44]]
    Qskew = Rotate(-np.pi / 4.0).dot(np.asarray(Qs)).dot(Rotate(np.pi / 4.0))
    return np.asarray(Qskew)


def Drift(L):
    D = [[1, L, 0, 0], 
         [0, 1, 0, 0], 
         [0, 0, 1, L], 
         [0, 0, 0, 1]]
    return np.asarray(D)


def RTFB(q1, q2, q3, d2, d3, L):
    if q2 < 0:
        RTFB_matrix = QskewFD(np.abs(q3), L).dot(Drift(d3)).dot(QskewDF(np.abs(q2), L)).dot(Drift(d2)).dot(QskewFD(np.abs(q1), L))
    else:
        RTFB_matrix = QskewDF(np.abs(q3), L).dot(Drift(d3)).dot(QskewFD(np.abs(q2), L)).dot(Drift(d2)).dot(QskewDF(np.abs(q1), L))
    return RTFB_matrix


def obj_function(params, sigma4, L):
    q1, q2, q3, d2, d3 = params
    sigmaF = RTFB(q1, q2, q3, d2, d3, L).dot(sigma4).dot(RTFB(q1, q2, q3, d2, d3, L).T)
    res = 1.0e6 * np.sqrt(sigmaF[0, 2]**2 + sigmaF[1, 2]**2 + sigmaF[0, 3]**2 + sigmaF[1, 3]**2)
    if not np.isfinite(res):
        res = 1.0e10
    return res


TASK_NAME = "Beamline Guru"
INPUT_LABELS = ["q1", "q2", "q3", "d2", "d3"]
BOUNDS = [(-10.0, 10.0)] * 5


def validate(data: Input) -> Result:
    if not isinstance(data, Input):
        data = Input(**data)

    params = [data.q1, data.q2, data.q3, data.d2, data.d3]

    time0 = time.time()
    res = obj_function(params, sigma4, L)
    time1 = time.time()
    dt = float(time1 - time0)

    if res < 1e-4:
        return Result(
            solved=True,
            score=1.0,
            message="Perfect match",
            evaltime=dt
        )
    else:
        score = float(res)
        if not np.isfinite(score):
            score = 1.0e10
        return Result(
            solved=False,
            score=score,
            message=f"Objective is {res}, expected minimal (less than 1e-4)",
            evaltime=dt
        )


# Task protocol constants (required by task_loader + job_manager)
TARGET = 0.0
MINIMIZE = True
FAILURE_SCORE = 1.0e10
MAX_VALIDATIONS_PER_USER = 10000
