# Repository Guidelines

## Project Structure & Module Organization

- `src/slacathon/` contains the FastAPI application, settings, SQLite storage,
  email service, middleware, job manager, and task loader.
- `src/slacathon/tasks/` contains pluggable optimization tasks and task data.
- `web/` contains HTML/Jinja templates and static assets.
- `tests/` contains pytest tests for registration, authentication, quotas,
  tasks, and leaderboard behavior.
- `clients/` contains example optimizer clients; `scripts/` contains operational
  utilities and the production start script.
- `kubernetes/base/` contains shared manifests. `kubernetes/overlays/dev/` and
  `kubernetes/overlays/prod/` contain environment-specific image, hostname, and
  Vault path patches.

## Build, Test, and Development Commands

Install the package and development dependencies with:

```bash
pip install -e '.[dev]'
```

Run the test suite:

```bash
pytest
```

Run the development server with reload:

```bash
PYTHONPATH=src uvicorn slacathon.main:app --host 127.0.0.1 --port 8000 --reload
```

Validate Kubernetes overlays before changing deployment files:

```bash
kubectl kustomize kubernetes/overlays/dev
kubectl kustomize kubernetes/overlays/prod
```

## Coding Style & Naming Conventions

Use Python 3.10+ with four-space indentation, type hints where practical, and
`snake_case` for modules, functions, and variables. Use `PascalCase` for
classes and uppercase names for environment variables and constants. Keep
settings under the `SLACATHON_` prefix and reuse existing settings/utilities
rather than adding parallel configuration paths.

## Testing Guidelines

Tests use pytest with `pytest-asyncio` and are located under `tests/`. Name test
files `test_*.py` and test functions `test_*`. Add regression coverage for
behavior changes, especially authentication, persistence, task selection, and
configuration. Run `pytest` before submitting changes.

## Commit & Pull Request Guidelines

Use the Conventional Commits format:

```text
<type>[optional scope]: <imperative description>
```

Use these types:

- `feat`: add user-visible functionality;
- `fix`: correct a defect;
- `refactor`: change internals without changing behavior;
- `test`: add or update tests;
- `docs`: update documentation;
- `chore`: maintain tooling, dependencies, or deployment configuration.

Examples:

```text
feat(tasks): add FEL surrogate task
fix(auth): reject expired verification tokens
chore(deploy): promote abc1234 to production
```

Use `!` or a `BREAKING CHANGE:` footer for incompatible changes. Keep the
subject concise and imperative. Pull requests should explain the behavioral
change, identify configuration or migration impact, and include the
verification commands run. Deployment changes should include rendered
Kustomize validation and should never commit Vault secret values.

## Security & Deployment Notes

Store runtime secrets only in Vault using the `ricoberger.de/v1alpha1`
`VaultSecret` resources. Use separate dev and prod Vault paths and keep the
Kubernetes Secret name `application-secrets`. Deploy immutable seven-character
image tags through `.github/workflows/deploy-dev.yml` and
`.github/workflows/promote-production.yml`; `latest` is only a fallback alias.
Deployment workflows create pull requests and do not push directly to `main`.
Production promotion requires the protected GitHub `production` Environment
approval. Argo CD watches `kubernetes/overlays/dev` and
`kubernetes/overlays/prod` in their respective clusters.
