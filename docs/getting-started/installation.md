# Installation

## Option A — Devcontainer (recommended)

Requirements: Docker Desktop, VS Code with Dev Containers extension.

1. Open the repo folder in VS Code.
2. Click **Reopen in Container** when prompted (or run `Dev Containers: Rebuild and Reopen in Container`).
3. VS Code builds the image, starts `app` + `mailpit` via `docker-compose.yml`.
4. Press **F5** (Run → **Run: FastAPI dev**) to start uvicorn with `--reload`.

App: `http://localhost:8000/slacathon26/`
Mailpit (email inspector): `http://localhost:8025`

No manual env configuration needed — the devcontainer pre-sets `SLACATHON_SMTP_HOST=mailpit`.

---

## Option B — Local (no Docker)

### Prerequisites

- Python ≥ 3.10
- A running SMTP server for email (or Mailpit — see below)

### Steps

```bash
# Clone
git clone https://github.com/slaclab/slacathon26.git
cd slacathon26

# Create and activate virtualenv
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install the package (editable)
pip install -e .

# Install dev extras (pytest, httpx)
pip install -e ".[dev]"
```

### Start a local mail catcher

Registration requires a working SMTP server. Mailpit provides a local inbox with a web UI.

```bash
docker run -d --name slacathon-mailpit \
  -p 1025:1025 -p 8025:8025 \
  axllent/mailpit:latest
```

Stop/remove: `docker rm -f slacathon-mailpit`

### Run the server

```bash
PYTHONPATH=src uvicorn slacathon.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

For a non-default task:

```bash
SLACATHON_ACTIVE_TASK=fel PYTHONPATH=src \
  uvicorn slacathon.main:app --host 127.0.0.1 --port 8000 --reload
```

See [Configuration](configuration.md) for all environment variables.

---

## Option C — Docker

```bash
docker build -t slacathon26 .
docker run -p 8000:8000 \
  -e SLACATHON_SMTP_HOST=host.docker.internal \
  -v $(pwd)/data:/app/data \
  slacathon26
```

See [deployment/docker.md](../deployment/docker.md) for full details.
