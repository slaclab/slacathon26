# Contributing

## Branching

- `main` is the integration branch. Direct pushes are protected by branch rulesets.
- Use short-lived feature branches: `feature/<description>`, `fix/<description>`, `chore/<description>`.
- Deployment branches (`deploy/dev-<sha7>`, `deploy/prod-<sha7>`) are managed by GitHub Actions — do not create these manually.

## Pull Request Workflow

1. Create a branch from latest `main`.
2. Make changes. Run tests: `pytest`.
3. Open a PR against `main`.
4. CI runs `release-build.yml` on merge; a new container image is published automatically.

## Code Style

- Python ≥ 3.10 features (union types with `|`, `match`, etc.) are fine.
- `pydantic` v2 patterns (`model_dump()`, `model_json_schema()`, `model_config`).
- No linter is configured in CI — follow the style visible in existing modules.

## Adding a New Task

See [Guides / Writing a Task](../guides/writing-a-task.md) for the task protocol.

## Dependency Changes

Add to `pyproject.toml` under `[project] dependencies`. Rebuild the devcontainer or re-run `pip install -e .` locally.

## Commit Message Convention

No strict enforced convention. Existing history uses `feat:`, `fix:`, `chore:` prefixes (Conventional Commits style). Follow that pattern for clarity.
