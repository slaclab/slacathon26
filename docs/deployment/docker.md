# Docker

## Dev Container

The `docker-compose.yml` defines two services:

| Service | Image | Purpose |
|---------|-------|---------|
| `app` | Built from `Dockerfile` | FastAPI application |
| `mailpit` | `axllent/mailpit:latest` | SMTP server + email web UI |

### Start

```bash
docker-compose up
```

The `app` service runs `sleep infinity` by default — start the server manually inside the container:

```bash
docker-compose exec app uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Ports

| Port | Service |
|------|---------|
| `8000` | FastAPI app |
| `1025` | Mailpit SMTP |
| `8025` | Mailpit web UI |

### Volume Mount

The project root is mounted at `/workspaces/slacathon26`. The `data/` directory (SQLite DB, leaderboard JSON) is also mounted so data persists across container restarts.

## Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /workspace
RUN apt-get update && apt-get install -y --no-install-recommends curl git
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["./start.sh"]
```

## Production Build

```bash
docker build -t slacathon26 .
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/workspace/data \
  -e SLACATHON_SMTP_HOST=<smtp-host> \
  -e SLACATHON_PUBLIC_URL=https://your-domain.com \
  -e SLACATHON_ALTCHA_HMAC_KEY=<strong-random-key> \
  slacathon26
```
