# Contributing

## Branching

- Main branch: `main`
- Feature branches: `feature/<short-description>`
- Bug fixes: `fix/<short-description>`

## Development Workflow

1. Create a feature branch from `main`
2. Make changes
3. Run tests: `python -m pytest`
4. Commit with a descriptive message
5. Open a pull request against `main`

## Code Style

- Python 3.11+
- No type annotation required but preferred on public functions
- No inline comments unless the WHY is non-obvious
- No docstrings on trivial functions

## Adding a New Task

See [Task Development Guide](../guides/task-development.md).

## Adding a New Endpoint

1. Add the route handler to the appropriate router in `app/routers/`
2. If it needs DB access, add `session: DBSession = Depends(get_session)` as a parameter
3. If it needs auth, add `api_key: str = Depends(verify_api_key)`
4. Add a test in the corresponding `tests/test_phase*.py` file

## Pull Requests

- Keep PRs focused — one feature or fix per PR
- Include a short description of what changed and why
- All tests must pass before merge
