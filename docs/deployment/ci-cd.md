# CI/CD

No CI/CD pipeline is currently configured in this repository. The following describes the recommended setup.

## Recommended Pipeline

```yaml
# .github/workflows/test.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m pytest
```

## Production Deployment

The current production deployment uses `start.sh`:

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 1 \
  --timeout 300 \
  --bind 127.0.0.1:8888 \
  --access-logfile gunicorn-access.log \
  --error-logfile gunicorn-error.log \
  app.main:app
```

The script sources a virtualenv at a hardcoded path — edit `start.sh` for other environments.
