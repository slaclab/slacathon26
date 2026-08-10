# Optimizer Clients

The `clients/` directory provides ready-made optimizers that work against any SLACathon task.

## Available Clients

| File | Method | Dependencies |
|---|---|---|
| `clients/gp_optimizer.py` | Gaussian Process (scikit-learn) | `numpy scipy scikit-learn` |
| `clients/xopt_optimizer.py` | Xopt Bayesian optimization | `xopt numpy requests` |
| `clients/usage.py` | GP optimizer usage example | same as GP |
| `clients/optimize_fel.py` | FEL task example (GP) | same as GP |

Install GP deps:

```bash
pip install numpy scipy scikit-learn
```

Install Xopt deps:

```bash
pip install xopt numpy requests
```

## GPOptimizer

`clients/gp_optimizer.py` implements a Bayesian optimizer with:

- **Exploration phase** — random sampling for the first N iterations
- **Exploitation phase** — GP + Lower Confidence Bound (LCB) acquisition function
- Automatic task discovery via `GET /task` (reads `parameter_labels` and `bounds`)

### Basic Usage

```python
from clients.gp_optimizer import GPOptimizer

optimizer = GPOptimizer(
    api_key="YOUR_API_KEY",
    base_url="http://localhost:8000/slacathon26"
)

best_x, best_score, best_result = optimizer.optimize(
    n_iterations=50,
    target_score=1e-4,
    exploration_iterations=10
)

# Submit best result
optimizer.submit_best_to_leaderboard(best_x)
```

### Key Methods

| Method | Description |
|---|---|
| `optimize(n_iterations, target_score, exploration_iterations)` | Run full optimization loop |
| `query_objective(x)` | POST to `/validate`, poll job, return `(score, result)` |
| `submit_to_leaderboard(x)` | POST to `/submit` |
| `view_leaderboard()` | GET `/leaderboard` |
| `get_history()` | GET `/history` |

### Validation Flow

`query_objective` calls `POST /validate` (async job) then polls `GET /jobs/{id}` until `status == "completed"`. This respects the server's async job model and avoids blocking the server.

## Xopt Optimizer

`clients/xopt_optimizer.py` wraps [Xopt](https://christophermayes.github.io/Xopt/) for modern Bayesian optimization. Refer to the file for usage and the [Xopt documentation](https://christophermayes.github.io/Xopt/) for configuration.

## Jupyter Notebooks

`notebooks/` contains:

- `GP-optimizer.ipynb` — interactive GP optimization walkthrough
- `Xopt-optimizer.ipynb` — Xopt optimization walkthrough

Install notebook deps:

```bash
pip install -e ".[notebooks]"
jupyter notebook notebooks/
```

## Task Discovery

All clients call `GET /task` at startup to read `parameter_labels` and `bounds`. No hardcoded parameters — the same client works for `flat_beam`, `fel`, or `cuinj` without modification.
