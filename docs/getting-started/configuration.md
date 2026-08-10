# Configuration

All settings use the `SLACATHON_` prefix and can be set via environment variables or `.env` file at the repo root. Values in `.env` are loaded by `pydantic-settings`.

```bash
cp .env.example .env
# Edit .env as needed
```

## All Settings

| Variable | Default | Required | Description |
|---|---|---|---|
| `SLACATHON_ACTIVE_TASK` | `flat_beam` | No | Task module to load (`flat_beam`, `fel`, `cuinj`) |
| `SLACATHON_ROOT_PATH` | `/slacathon26` | No | FastAPI `root_path` mount prefix |
| `SLACATHON_HOST` | `127.0.0.1` | No | Bind address (Gunicorn) |
| `SLACATHON_PORT` | `8888` | No | Bind port (Gunicorn) |
| `SLACATHON_WORKERS` | `1` | No | Number of workers — keep at 1 (SQLite constraint) |
| `SLACATHON_TIMEOUT` | `300` | No | Gunicorn worker timeout (seconds) |
| `SLACATHON_LOG_LEVEL` | `info` | No | Logging verbosity (`debug`, `info`, `warning`, `error`) |
| `SLACATHON_DB_FILE` | `data/slacathon.db` | No | SQLite database path |
| `SLACATHON_LEADERBOARD_FILE` | `data/leaderboard.json` | No | Leaderboard JSON path |
| `SLACATHON_MAX_QUERIES_PER_USER` | `10` | No | In-memory history buffer size per user |
| `SLACATHON_MAX_VALIDATIONS_PER_USER` | `10000` | No | Hard quota per user (overridden by task constant) |
| `SLACATHON_LEADERBOARD_SIZE` | `15` | No | Maximum leaderboard entries |
| `SLACATHON_FAILURE_SCORE` | `1e10` | No | Score returned on task error (fallback) |
| `SLACATHON_PUBLIC_URL` | `http://localhost:8000` | **Yes (prod)** | Base URL for email verification links |
| `SLACATHON_SMTP_HOST` | `localhost` | **Yes (prod)** | SMTP server hostname |
| `SLACATHON_SMTP_PORT` | `1025` | No | SMTP port |
| `SLACATHON_SMTP_FROM` | `noreply@slacathon26.local` | **Yes (prod)** | Sender address |
| `SLACATHON_ALTCHA_HMAC_KEY` | `dev-hmac-key-change-in-prod` | **Yes (prod)** | CAPTCHA signing secret — change before deploying |
| `SLACATHON_VERIFY_TIMEOUT_HOURS` | `24` | No | Verification link lifetime |
| `SLACATHON_CLEANUP_INTERVAL_MINUTES` | `10` | No | Expired-user cleanup frequency |

## Task-specific Variables

| Variable | Task | Description |
|---|---|---|
| `FEL_URL` | `fel` | FEL model service endpoint (default: SLAC ARD service) |
| `CUINJ_URL` | `cuinj` | CUINJ model service endpoint (default: SLAC ARD service) |

## Kubernetes Secrets (production)

In Kubernetes the following four variables are injected from Vault (see [deployment/kubernetes.md](../deployment/kubernetes.md)):

- `SLACATHON_ALTCHA_HMAC_KEY`
- `SLACATHON_PUBLIC_URL`
- `SLACATHON_SMTP_HOST`
- `SLACATHON_SMTP_FROM`

Remaining non-secret config is in `kubernetes/base/configmap.yaml`.
