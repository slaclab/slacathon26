import logging
import time
from typing import Optional

import numpy as np
import requests
from scipy.optimize import minimize
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF

logger = logging.getLogger(__name__)


class GPOptimizer:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        })

        self.task_info = self._request("GET", "/task")
        self.input_labels = self.task_info.get("parameter_labels") or ["x1", "x2", "x3", "x4", "x5"]
        self.dim = len(self.input_labels)
        self.bounds = self.task_info.get("bounds") or [(-10.0, 10.0)] * self.dim

        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(length_scale=1.0, length_scale_bounds=(1e-2, 1e2))
        self.gp = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=10,
            alpha=1e-6,
            normalize_y=True
        )

        self.X_observed: list[np.ndarray] = []
        self.y_observed: list[float] = []

        logger.info(f"GPOptimizer initialized for task: {self.task_info.get('name')}, dim={self.dim}")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"{method} {path} failed: {e}")
            return {}

    def _wait_for_job(self, job_id: str, timeout: float = 300.0, poll_interval: float = 1.5) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self._request("GET", f"/jobs/{job_id}")
            status = data.get("status")
            if status == "completed":
                return data.get("result", {})
            if status == "failed":
                logger.warning(f"Job {job_id} failed")
                return {}
            time.sleep(poll_interval)
        logger.warning(f"Job {job_id} timed out after {timeout}s")
        return {}

    def query_objective(self, x: np.ndarray) -> tuple[float, dict]:
        input_dict = {label: float(val) for label, val in zip(self.input_labels, x)}
        logger.info(f"Querying with input: {input_dict}")

        job = self._request("POST", "/validate", json={"input": input_dict})
        job_id = job.get("job_id")
        if not job_id:
            logger.error("Failed to create validation job")
            return float("inf"), {}

        result = self._wait_for_job(job_id)
        if not result:
            return float("inf"), {}

        score = result.get("score", float("inf"))
        logger.info(f"Job {job_id} done → score={score:.6f}, solved={result.get('solved')}")
        return score, result

    def submit_to_leaderboard(self, x: np.ndarray) -> dict:
        input_dict = {label: float(val) for label, val in zip(self.input_labels, x)}
        result = self._request("POST", "/submit", json={"input": input_dict}, timeout=15)
        if result:
            logger.info(f"Leaderboard submit → rank {result.get('rank')}/{result.get('leaderboard_size')}")
        return result

    def view_leaderboard(self) -> dict:
        return self._request("GET", "/leaderboard")

    def get_history(self) -> Optional[dict]:
        return self._request("GET", "/history")

    def acquisition_function(self, x: np.ndarray) -> float:
        if not self.X_observed:
            return 0.0
        try:
            mu, sigma = self.gp.predict(x.reshape(1, -1), return_std=True)
            return (mu - 2.0 * sigma)[0]  # LCB for minimization
        except Exception:
            return np.random.randn()

    def suggest_next_point(self, bounds: list[tuple] = None, n_restarts: int = 8) -> np.ndarray:
        if bounds is None:
            bounds = self.bounds
        if len(self.X_observed) < 3:
            return np.array([np.random.uniform(lo, hi) for lo, hi in bounds])

        best_x, best_val = None, float("inf")
        for _ in range(n_restarts):
            x0 = np.array([np.random.uniform(lo, hi) for lo, hi in bounds])
            res = minimize(self.acquisition_function, x0, bounds=bounds, method="L-BFGS-B")
            if res.success and res.fun < best_val:
                best_val = res.fun
                best_x = res.x
        return best_x if best_x is not None else np.array([np.random.uniform(lo, hi) for lo, hi in bounds])

    def optimize(self,
                 bounds: list[tuple] = None,
                 n_iterations: int = 50,
                 target_score: float = 1e-3,
                 exploration_iterations: int = 10) -> tuple[Optional[np.ndarray], float, dict]:
        if bounds is None:
            bounds = self.bounds
        logger.info(f"Starting GP optimization for task (target < {target_score})")

        best_x: Optional[np.ndarray] = None
        best_score = float("inf")
        best_result: dict = {}

        for i in range(n_iterations):
            logger.info(f"Iter {i+1}/{n_iterations}")

            if i < exploration_iterations:
                x = np.array([np.random.uniform(lo, hi) for lo, hi in bounds])
            else:
                x = self.suggest_next_point(bounds)

            score, result = self.query_objective(x)
            if score == float("inf"):
                continue

            self.X_observed.append(x)
            self.y_observed.append(score)

            if score < best_score:
                best_score = score
                best_x = x
                best_result = result
                logger.info(f"New best: {best_score:.6f} @ {best_x}")

            if len(self.X_observed) >= 3:
                X = np.array(self.X_observed)
                y = np.array(self.y_observed)
                if np.all(np.isfinite(y)):
                    try:
                        self.gp.fit(X, y)
                    except Exception as e:
                        logger.warning(f"GP fit failed: {e}")

            if best_score < target_score:
                logger.info(f"Target reached: {best_score:.6f}")
                break

            time.sleep(1.0)

        logger.info(f"Done. Best score={best_score:.6f}, x={best_x}")
        if best_result:
            logger.info(f"Solved={best_result.get('solved')}, msg={best_result.get('message')}")
        return best_x, best_score, best_result

    def submit_best_to_leaderboard(self, x: np.ndarray) -> dict:
        return self.submit_to_leaderboard(x)
