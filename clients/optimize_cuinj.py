"""
Run the GP optimizer against a local server serving the injector task.

Start the server first with the injector task active, e.g.:
    ACTIVE_TASK=cuinj .venv/bin/uvicorn main:app --reload --port 8000

The injector score is the combined transverse emittance in um (lower is better),
so the platform's minimize convention applies directly. The task has no solved
threshold, so target_score=0.0 keeps the run going for the full budget and just
drives the emittance as low as it can.
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
        target_score=0.0,
        exploration_iterations=10,
    )

    if best_x is not None:
        opt.submit_best_to_leaderboard(best_x)