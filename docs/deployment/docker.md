# Docker

## Image

The published image is `ghcr.io/slaclab/slacathon26`.

Tags:
- `<sha7>` — immutable, tied to a specific commit. Always use this for deployments.
- `latest` — convenience alias pointing to the most recent build. Do not use in production.

## Building Locally

```bash
docker build -t slacathon26:local .
```

The `Dockerfile` uses `python:3.11-slim`, installs dependencies first (layer-cached), then copies source.

## Running Locally

```bash
docker run -p 8000:8000 \
  -e SLACATHON_SMTP_HOST=host.docker.internal \
  -e SLACATHON_PUBLIC_URL=http://localhost:8000 \
  -e SLACATHON_ALTCHA_HMAC_KEY=dev-key \
  -v $(pwd)/data:/app/data \
  slacathon26:local
```

App: `http://localhost:8000/slacathon26/`

## Volumes

| Container path | Purpose |
|---|---|
| `/app/data` | SQLite DB + leaderboard JSON. Mount a host volume to persist data across restarts. |

## Environment Variables

See [Configuration](../getting-started/configuration.md) for the full list. At minimum, set for production:

- `SLACATHON_PUBLIC_URL`
- `SLACATHON_SMTP_HOST`
- `SLACATHON_SMTP_FROM`
- `SLACATHON_ALTCHA_HMAC_KEY`

## Devcontainer

`docker-compose.yml` defines the VS Code devcontainer environment:

- `app` service — mounts the repo as a workspace, exposes port 2222 for VS Code remote.
- `mailpit` service — local SMTP + web UI for email testing.

The devcontainer is for development only; it runs `sleep infinity` and relies on VS Code to start the actual server process.
