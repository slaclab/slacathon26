# Installation

## Prerequisites

- Python 3.11+
- Git

## Steps

```bash
# 1. Clone
git clone <repo-url>
cd slacathon26

# 2. Create virtualenv
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set SLACATHON_SMTP_HOST and SLACATHON_PUBLIC_URL

# 5. Start (development)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Application is available at `http://localhost:8000/slacathon26`.

## Dev Container (VS Code)

The repo includes a `.devcontainer/devcontainer.json` that provisions the full stack:

1. Open the repo in VS Code
2. Click **Reopen in Container** when prompted
3. The container installs dependencies and starts Mailpit automatically

Forwarded ports:
- `8000` — FastAPI app
- `8025` (mapped from `mailpit:8025`) — Mailpit web UI for email inspection

## Data Directory

The app creates `data/slacathon26.db` (SQLite) on first startup. The `data/` directory must be writable.

```bash
mkdir -p data
```

## Next Steps

- [Configuration](configuration.md) — full environment variable reference
- [Quickstart](quickstart.md) — first API call in under 2 minutes
