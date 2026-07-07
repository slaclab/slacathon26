# Local Development Setup

## Prerequisites

- Python 3.11+
- Git
- (Optional) VS Code with Dev Containers extension

## Option 1: Dev Container (Recommended)

The repo ships with a `.devcontainer/devcontainer.json` that starts the full stack automatically.

1. Install [VS Code](https://code.visualstudio.com/) and the **Dev Containers** extension
2. Open the repo folder in VS Code
3. Click **Reopen in Container** when prompted

The container:
- Installs all Python dependencies via `pip install -r requirements.txt`
- Starts a Mailpit SMTP server (web UI at `localhost:8025`)
- Forwards ports `8000` (app) and `8025` (Mailpit)

Start the server inside the container:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Option 2: Manual Setup

```bash
# Clone and set up virtualenv
git clone <repo-url>
cd slacathon26
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — set SLACATHON_SMTP_HOST, SLACATHON_PUBLIC_URL

# Start Mailpit (for email testing)
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit

# Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Accessing the App

| URL | Description |
|-----|-------------|
| `http://localhost:8000/slacathon26/` | Landing page |
| `http://localhost:8000/slacathon26/register` | Registration form |
| `http://localhost:8000/slacathon26/board` | Leaderboard page |
| `http://localhost:8000/slacathon26/task` | Active task JSON |
| `http://localhost:8000/docs` | FastAPI Swagger UI |
| `http://localhost:8025` | Mailpit UI (intercepted emails) |

## Dev Seed Keys

The first startup seeds three API keys into the database:

| Key | User |
|-----|------|
| `key_123` | Alex |
| `key_456` | Chris |
| `key_789` | Ken |

Use these directly with the API — no registration required in development.

## VS Code Launch Configs

`.vscode/launch.json` includes a **Run Backend (uvicorn dev)** config with all required environment variables pre-filled. Use F5 to start with the debugger attached.

## Switching Tasks

```bash
SLACATHON_ACTIVE_TASK=flat_beam uvicorn app.main:app --reload
```

Or set `SLACATHON_ACTIVE_TASK` in `.env`.
