import numpy as np
from gp_optimizer import GPOptimizer

API_KEY = "YOUR_API_KEY_FROM_VERIFICATION_EMAIL"
BASE_URL = "https://halavanau.group/slacathon26"

FIXED_VALUES = [1.0, 1.4]
BOUNDS = [(1.0, 3.0), (-3.0, -2.0), (0.0, 2.0)]

optimizer = GPOptimizer(api_key=API_KEY, base_url=BASE_URL)

orig_query = optimizer.query_objective
orig_submit = optimizer.submit_to_leaderboard

def make_full(x):
    return list(x) + FIXED_VALUES

optimizer.query_objective = lambda x: orig_query(np.array(make_full(x)))
optimizer.submit_to_leaderboard = lambda x: orig_submit(np.array(make_full(x)))

best_x, best_score, best_result = optimizer.optimize(
    bounds=BOUNDS, n_iterations=250, target_score=1e-3, exploration_iterations=10
)

print("OPTIMIZATION COMPLETE")
if best_x is not None:
    full = list(best_x) + FIXED_VALUES
    print(f"optimized: {best_x}")
    print(f"fixed: {FIXED_VALUES}")
    print(f"full: {full}")
    print(f"score: {best_score:.6f}")
    if best_result:
        print(f"solved={best_result.get('solved')}")
    sub = optimizer.submit_best_to_leaderboard(best_x)
    print(f"submitted rank: {sub.get('rank') if sub else 'n/a'}")
else:
    print("no solution")
