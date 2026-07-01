import logging
import time
from typing import Optional

import numpy as np
import requests

logger = logging.getLogger(__name__)

try:
    from xopt import Xopt
    from xopt.vocs import VOCS
    from xopt.evaluator import Evaluator
    from xopt.generators.bayesian import UpperConfidenceBoundGenerator
    XOPT_AVAILABLE = True
except ImportError:
    XOPT_AVAILABLE = False


class XoptOptimizer:
    """
    Lightweight client for running Xopt on the SLACATHON API.

    This follows the standard Xopt usage pattern:

        vocs = client.vocs
        evaluator = Evaluator(function=client.evaluate)
        generator = UpperConfidenceBoundGenerator(vocs=vocs)
        X = Xopt(evaluator=evaluator, generator=generator, vocs=vocs)

        X.random_evaluate(3)
        for _ in range(20):
            X.step()

        print(X.data)
        best = vocs.select_best(X.data)

    It also provides a convenient .optimize() method that returns
    results in a similar shape to GPOptimizer for easy comparison.
    """

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
        self.bounds = self.task_info.get("bounds") or [(-10.0, 10.0)] * len(self.input_labels)

        logger.info(f"XoptOptimizer initialized for task: {self.task_info.get('name')}")

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

    @property
    def vocs(self):
        """Return a VOCS object built from the remote task definition."""
        if not XOPT_AVAILABLE:
            raise ImportError("xopt is required to create a VOCS object. pip install xopt")
        return VOCS(
            variables={label: [float(lo), float(hi)] for label, (lo, hi) in zip(self.input_labels, self.bounds)},
            objectives={"score": "MINIMIZE"},
        )

    def evaluate(self, inputs: dict) -> dict:
        """
        Xopt-compatible evaluation function.

        Takes a dict of the form {"q1": 1.2, "q2": -0.5, ...}
        Returns at least {"score": float}. Extra keys are stored by Xopt.
        """
        x = np.array([inputs[label] for label in self.input_labels])
        input_dict = {label: float(val) for label, val in zip(self.input_labels, x)}

        # Call the API
        job = self._request("POST", "/validate", json={"input": input_dict})
        job_id = job.get("job_id")
        if not job_id:
            return {"score": 1.0e10, "error": "failed to create job"}

        result = self._wait_for_job(job_id)

        score = result.get("score", 1.0e10) if result else 1.0e10
        if not np.isfinite(score):
            score = 1.0e10

        return {
            "score": float(score),
            "solved": result.get("solved", False) if result else False,
            "message": result.get("message", "") if result else "",
            "evaltime": result.get("evaltime", 0.0) if result else 0.0,
        }

    def query_objective(self, x: np.ndarray) -> tuple[float, dict]:
        """Convenience method compatible with GPOptimizer-style usage."""
        input_dict = {label: float(val) for label, val in zip(self.input_labels, x)}
        job = self._request("POST", "/validate", json={"input": input_dict})
        job_id = job.get("job_id")
        if not job_id:
            return float("inf"), {}
        result = self._wait_for_job(job_id)
        score = result.get("score", float("inf")) if result else float("inf")
        return score, (result or {})

    def submit_to_leaderboard(self, x: np.ndarray) -> dict:
        input_dict = {label: float(val) for label, val in zip(self.input_labels, x)}
        return self._request("POST", "/submit", json={"input": input_dict}, timeout=15)

    def submit_best_to_leaderboard(self, x: np.ndarray) -> dict:
        return self.submit_to_leaderboard(x)

    def view_leaderboard(self) -> dict:
        return self._request("GET", "/leaderboard")

    def get_history(self) -> Optional[dict]:
        return self._request("GET", "/history")

    def optimize(
        self,
        bounds: list[tuple] = None,
        n_iterations: int = 50,
        target_score: float = 1e-3,
        n_initial: int = 5,
        **xopt_options,
    ) -> tuple[Optional[np.ndarray], float, dict]:
        """
        High-level convenience method that follows the standard Xopt pattern
        under the hood and returns (best_x, best_score, result) for compatibility.
        """
        if not XOPT_AVAILABLE:
            raise ImportError("pip install xopt is required to use optimize()")

        if bounds is None:
            bounds = self.bounds

        vocs = self.vocs
        evaluator = Evaluator(function=self.evaluate)
        generator = UpperConfidenceBoundGenerator(vocs=vocs)

        X = Xopt(
            vocs=vocs,
            evaluator=evaluator,
            generator=generator,
            **xopt_options,
        )

        logger.info(f"Starting Xopt optimization, target < {target_score}")

        if n_initial > 0:
            X.random_evaluate(n_initial)

        for _ in range(n_iterations):
            X.step()
            if len(X.data) > 0:
                current_best = X.data["score"].min()
                if current_best < target_score:
                    logger.info(f"Target reached: {current_best:.6f}")
                    break

        df = X.data
        if len(df) == 0 or "score" not in df.columns:
            return None, float("inf"), {}

        best_idx = df["score"].idxmin()
        best_row = df.loc[best_idx]

        best_x = np.array([best_row[label] for label in self.input_labels])
        best_score = float(best_row["score"])

        best_result = {
            "score": best_score,
            "solved": bool(best_row.get("solved", False)),
            "message": best_row.get("message", ""),
            "evaltime": float(best_row.get("evaltime", 0.0)),
        }

        # Expose the full Xopt object for advanced use
        self.xopt = X

        logger.info(f"Done. Best score={best_score:.6f}")
        return best_x, best_score, best_result
