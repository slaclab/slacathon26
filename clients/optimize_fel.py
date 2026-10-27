"""
Run the GP optimizer against a local server serving the FEL task.

Start the server first (all tasks are served at once), e.g.:
    PYTHONPATH=src uvicorn slacathon.main:app --reload --port 8000

The FEL score is -hxr_pulse_intensity (the platform minimizes), so a lower
score means a brighter pulse. The task is solved at 4 mJ, i.e. score <= -4.
"""

import logging
import os

from gp_optimizer import GPOptimizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

API_KEY = os.getenv("API_KEY", "dev_key")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

if __name__ == "__main__":
    opt = GPOptimizer(api_key=API_KEY, base_url=BASE_URL, public_task_id="fel")

    best_x, best_score, best_result = opt.optimize(
        n_iterations=50,
        target_score=-5.5,
        exploration_iterations=10,
    )

    if best_x is not None:
        opt.submit_best_to_leaderboard(best_x)