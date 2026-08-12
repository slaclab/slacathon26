"""
Run the GP optimizer against a local server serving the FEL task.

Start the server first with the FEL task active, e.g.:
    ACTIVE_TASK=fel .venv/bin/uvicorn main:app --reload --port 8000

The FEL score is -hxr_pulse_intensity (the platform minimizes), so a lower
score means a brighter pulse. The task is solved at 4 mJ, i.e. score <= -4.
"""

import logging
import os

from gp_optimizer import GPOptimizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

API_KEY = os.environ["API_KEY"]
BASE_URL = os.getenv("BASE_URL", "https://ad-accel-online-ml-dev.slac.stanford.edu/slacathon26/")

if __name__ == "__main__":
    opt = GPOptimizer(api_key=API_KEY, base_url=BASE_URL)

    best_x, best_score, best_result = opt.optimize(
        n_iterations=50,
        target_score=-5.5,
        exploration_iterations=10,
    )

    if best_x is not None:
        opt.submit_best_to_leaderboard(best_x)