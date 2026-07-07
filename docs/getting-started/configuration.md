# Configuration

All settings are read from environment variables with the `SLACATHON_` prefix. A `.env` file in the project root is loaded automatically.

## Full Reference

### Task & Routing

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_ACTIVE_TASK` | `flat_beam` | Module name in `app/tasks/` to load |
| `SLACATHON_ROOT_PATH` | `/slacathon26` | FastAPI `root_path` (affects URL prefix behind a reverse proxy) |

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_HOST` | `127.0.0.1` | Bind address |
| `SLACATHON_PORT` | `8888` | Bind port |
| `SLACATHON_WORKERS` | `1` | Gunicorn worker count |
| `SLACATHON_TIMEOUT` | `300` | Request timeout (seconds) |
| `SLACATHON_LOG_LEVEL` | `info` | Logging level (`debug`/`info`/`warning`/`error`) |

### API Keys (Legacy)

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_API_KEYS` | `""` | Comma or space-separated list of static API keys (pre-registration) |

> Note: Registered users have their own API keys stored in the database. `SLACATHON_API_KEYS` is for dev seeding only.

### Quotas & Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_MAX_QUERIES_PER_USER` | `10` | Max history entries returned by `/history` |
| `SLACATHON_MAX_VALIDATIONS_PER_USER` | `10000` | Per-user validation cap (overridden by task) |
| `SLACATHON_LEADERBOARD_SIZE` | `15` | Maximum leaderboard entries |
| `SLACATHON_FAILURE_SCORE` | `1.0e10` | Score assigned to failed/invalid submissions |

### Email (SMTP)

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_SMTP_HOST` | `localhost` | SMTP server hostname |
| `SLACATHON_SMTP_PORT` | `1025` | SMTP port |
| `SLACATHON_SMTP_FROM` | `noreply@slacathon26.local` | From address for outbound email |
| `SLACATHON_PUBLIC_URL` | `http://localhost:8000` | Base URL inserted into verification links |

### Registration

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_VERIFY_TIMEOUT_HOURS` | `24` | Hours before unverified registration expires |
| `SLACATHON_CLEANUP_INTERVAL_MINUTES` | `10` | How often to run expired-user cleanup |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACATHON_ALTCHA_HMAC_KEY` | `dev-hmac-key-change-in-prod` | HMAC key for Altcha CAPTCHA signing — **change in production** |

## Example .env (development)

```bash
SLACATHON_ACTIVE_TASK=flat_beam
SLACATHON_ROOT_PATH=/slacathon26
SLACATHON_PORT=8000
SLACATHON_SMTP_HOST=mailpit
SLACATHON_SMTP_PORT=1025
SLACATHON_SMTP_FROM=noreply@slacathon26.local
SLACATHON_PUBLIC_URL=http://localhost:8000
SLACATHON_ALTCHA_HMAC_KEY=dev-hmac-key-change-in-prod
SLACATHON_VERIFY_TIMEOUT_HOURS=24
```
