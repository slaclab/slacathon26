# Phase 08 — Docker Compose & Dev Container Update

## Scope
Add `docker-compose.yml` with app + Mailpit.
Update `.devcontainer/devcontainer.json` to use compose.
No Python code changes.

## Prereq
All prior phases (Phases 01–07) — app must work standalone before wrapping in compose.

## Files Created / Modified
| File | Change |
|---|---|
| `docker-compose.yml` | New — app + mailpit services |
| `.devcontainer/devcontainer.json` | Update to use compose |
| `.env.example` | Add new env vars |

---

## `docker-compose.yml`

```yaml
version: "3.9"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/workspace
      - ./data:/workspace/data
    environment:
      - SLACATHON_SMTP_HOST=mailpit
      - SLACATHON_SMTP_PORT=1025
      - SLACATHON_PUBLIC_URL=http://localhost:8000
    depends_on:
      - mailpit
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"
      - "8025:8025"
    restart: unless-stopped
```

---

## `.devcontainer/devcontainer.json`

```json
{
  "name": "SLACATHON 26 Dev",
  "dockerComposeFile": "../docker-compose.yml",
  "service": "app",
  "workspaceFolder": "/workspace",
  "forwardPorts": [8000, 8025],
  "portsAttributes": {
    "8000": { "label": "FastAPI" },
    "8025": { "label": "Mailpit UI" }
  },
  "postCreateCommand": "pip install -r requirements.txt",
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "ms-python.vscode-pylance"]
    }
  }
}
```

---

## `.env.example` additions

Append to existing `.env.example`:

```
# SMTP (Mailpit in dev, real relay in prod)
SLACATHON_SMTP_HOST=localhost
SLACATHON_SMTP_PORT=1025
SLACATHON_SMTP_FROM=noreply@slacathon26.local

# Public URL (base for verification links)
SLACATHON_PUBLIC_URL=http://localhost:8000

# Altcha (self-hosted PoW CAPTCHA — no external service, change key in prod)
SLACATHON_ALTCHA_HMAC_KEY=dev-hmac-key-change-in-prod

# Registration
SLACATHON_VERIFY_TIMEOUT_HOURS=24
SLACATHON_CLEANUP_INTERVAL_MINUTES=10
```

---

## Acceptance Criteria
- `docker compose up` starts both services without error
- `http://localhost:8025` shows Mailpit web UI
- `http://localhost:8000/slacathon26/register` serves the registration page
- Registration sends email visible in Mailpit UI
- Dev container opens in VS Code with ports 8000 and 8025 forwarded

---

## Test Suite: `tests/test_phase08_compose.py`

```python
"""
Phase 08 — docker-compose and devcontainer config structure tests.
These are static/structural checks — no Docker daemon required.
"""
import pytest
import yaml
import json
from pathlib import Path


def test_docker_compose_exists():
    assert Path("docker-compose.yml").exists()


def test_docker_compose_services():
    with open("docker-compose.yml") as f:
        cfg = yaml.safe_load(f)
    services = cfg.get("services", {})
    assert "app" in services
    assert "mailpit" in services


def test_docker_compose_mailpit_ports():
    with open("docker-compose.yml") as f:
        cfg = yaml.safe_load(f)
    ports = cfg["services"]["mailpit"]["ports"]
    port_strs = [str(p) for p in ports]
    assert any("8025" in p for p in port_strs)
    assert any("1025" in p for p in port_strs)


def test_docker_compose_app_depends_on_mailpit():
    with open("docker-compose.yml") as f:
        cfg = yaml.safe_load(f)
    depends = cfg["services"]["app"].get("depends_on", [])
    assert "mailpit" in depends


def test_devcontainer_uses_compose():
    path = Path(".devcontainer/devcontainer.json")
    assert path.exists()
    with open(path) as f:
        cfg = json.load(f)
    assert "dockerComposeFile" in cfg
    assert cfg.get("service") == "app"


def test_devcontainer_forwards_mailpit_port():
    with open(".devcontainer/devcontainer.json") as f:
        cfg = json.load(f)
    ports = cfg.get("forwardPorts", [])
    assert 8025 in ports


def test_env_example_has_new_vars():
    path = Path(".env.example")
    assert path.exists()
    content = path.read_text()
    for var in ["SLACATHON_SMTP_HOST", "SLACATHON_PUBLIC_URL",
                "SLACATHON_ALTCHA_HMAC_KEY", "SLACATHON_VERIFY_TIMEOUT_HOURS"]:
        assert var in content, f"{var} missing from .env.example"
```
