import numpy as np
from xopt_optimizer import XoptOptimizer

from xopt import Xopt, Evaluator, VOCS
from xopt.generators.bayesian import UpperConfidenceBoundGenerator

API_KEY = "YOUR_API_KEY_FROM_VERIFICATION_EMAIL"
BASE_URL = "https://halavanau.group/slacathon26"

# Fixed values for some parameters (we discover which ones are fixed automatically below)
FIXED_VALUES = [1.0, 1.4]

# Free variables we want to optimize over
FREE_LABELS = ["q1", "q2", "q3"]
FREE_BOUNDS = [(1.0, 3.0), (-3.0, -2.0), (0.0, 2.0)]

client = XoptOptimizer(api_key=API_KEY, base_url=BASE_URL)

print("Task input labels from server:", client.input_labels)

# Automatically figure out which labels are fixed (the ones not in FREE_LABELS)
fixed_labels = [lbl for lbl in client.input_labels if lbl not in FREE_LABELS]
assert len(fixed_labels) == len(FIXED_VALUES), "Number of fixed values must match number of fixed labels"

# Create a VOCS using only the free variables
vocs = VOCS(
    variables={label: list(bnd) for label, bnd in zip(FREE_LABELS, FREE_BOUNDS)},
    objectives={"score": "MINIMIZE"},
)

def evaluate_fixed(inputs: dict) -> dict:
    """Inject the fixed parameters (using labels discovered from the task), then evaluate."""
    full_inputs = dict(inputs)  # copy the free variables

    # Inject fixed values
    for label, value in zip(fixed_labels, FIXED_VALUES):
        full_inputs[label] = value

    # Build the full array in the exact order the task expects
    full_x = np.array([full_inputs[label] for label in client.input_labels])

    score, result = client.query_objective(full_x)

    return {
        "score": score if np.isfinite(score) else 1e10,
        "solved": result.get("solved", False),
        "message": result.get("message", ""),
        "evaltime": result.get("evaltime", 0.0),
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

# Get best from the DataFrame directly (more reliable than select_best which returns a tuple)
if len(X.data) > 0 and 'score' in X.data.columns:
    best_idx = X.data['score'].idxmin()
    best_row = X.data.loc[best_idx]

    best_x = np.array([best_row[label] for label in FREE_LABELS])
    full_input_dict = {label: val for label, val in zip(FREE_LABELS, best_x)}
    for label, val in zip(fixed_labels, FIXED_VALUES):
        full_input_dict[label] = val
    full_x = np.array([full_input_dict[label] for label in client.input_labels])

    print(f"\nBest (free): {best_x}")
    print(f"Full input:  {full_x}")
    print(f"Best score:  {best_row['score']:.6f}")

    sub = client.submit_to_leaderboard(full_x)
    if sub:
        print(f"Submitted! Rank: {sub.get('rank')}/{sub.get('leaderboard_size')}")
else:
    print("No valid result found.")

print("\n" + "="*60)
print("CURRENT LEADERBOARD")
print("="*60)
response = client.view_leaderboard()
if response:
    for i, entry in enumerate(response.get('leaderboard', []), 1):
        solved_marker = "✓" if entry.get('solved', False) else "✗"
        print(f"{i:2d}. [{solved_marker}] Score: {entry.get('score', 0):8.6f} | User: {entry.get('user', 'Unknown')}")
    print(f"\nTotal entries: {response.get('total_entries', 'N/A')}")
