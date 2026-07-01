import numpy as np
from XoptOptimizer import XoptOptimizer

from xopt import Xopt, Evaluator, VOCS
from xopt.generators.bayesian import UpperConfidenceBoundGenerator

API_KEY = "key_123"
BASE_URL = "https://halavanau.group/slacathon26"

FIXED_VALUES = [1.0, 1.4]
FREE_LABELS = ["q1", "q2", "q3"]
FREE_BOUNDS = [(1.0, 3.0), (-3.0, -2.0), (0.0, 2.0)]

client = XoptOptimizer(api_key=API_KEY, base_url=BASE_URL)

# For fixed parameters, we define VOCS with only the free variables
vocs = VOCS(
    variables={label: bnd for label, bnd in zip(FREE_LABELS, FREE_BOUNDS)},
    objectives={"score": "MINIMIZE"},
)

def evaluate_fixed(inputs: dict) -> dict:
    """Inject fixed parameters before calling the backend."""
    full_inputs = {**inputs, "q4": FIXED_VALUES[0], "q5": FIXED_VALUES[1]}
    score, result = client.query_objective(
        np.array([full_inputs[lbl] for lbl in client.input_labels])
    )
    return {
        "score": score if np.isfinite(score) else 1e10,
        "solved": result.get("solved", False),
        "message": result.get("message", ""),
    }

evaluator = Evaluator(function=evaluate_fixed)
generator = UpperConfidenceBoundGenerator(vocs=vocs)

X = Xopt(evaluator=evaluator, generator=generator, vocs=vocs)

print("Running Xopt optimization with fixed parameters...")
X.random_evaluate(5)
for _ in range(30):
    X.step()

print("\nOptimization results:")
print(X.data.tail())

best = vocs.select_best(X.data)
if best is not None:
    best_x = np.array([best[label] for label in FREE_LABELS])
    full_x = list(best_x) + FIXED_VALUES
    print(f"\nBest (free): {best_x}")
    print(f"Full input:  {full_x}")
    print(f"Best score:  {best['score']:.6f}")

    sub = client.submit_to_leaderboard(np.array(full_x))
    if sub:
        print(f"Submitted! Rank: {sub.get('rank')}/{sub.get('leaderboard_size')}")
else:
    print("No valid result found.")