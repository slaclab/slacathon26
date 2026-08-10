# Production Environment

## Source of Config

In Kubernetes, config comes from two sources:

| Source | K8s resource | Env vars |
|---|---|---|
| ConfigMap | `slacathon26-config` | Non-secret operational config |
| VaultSecret → K8s Secret | `application-secrets` | Secrets injected from HashiCorp Vault |

## ConfigMap Values (kubernetes/base/configmap.yaml)

| Key | Value | Notes |
|---|---|---|
| `SLACATHON_ACTIVE_TASK` | `flat_beam` | Change to `fel` or `cuinj` to switch challenge |
| `SLACATHON_ROOT_PATH` | `/slacathon26` | Must match ingress path prefix |
| `SLACATHON_DB_FILE` | `/app/data/slacathon.db` | Path on PVC |
| `SLACATHON_LEADERBOARD_FILE` | `/app/data/leaderboard.json` | Path on PVC |
| `SLACATHON_SMTP_PORT` | `587` | Standard TLS SMTP |
| `SLACATHON_LOG_LEVEL` | `info` | |

## Vault Secret Keys

Populate both Vault paths with these four keys before first deploy:

| Key | Purpose |
|---|---|
| `SLACATHON_ALTCHA_HMAC_KEY` | Signs CAPTCHA challenges. Use a strong random string. |
| `SLACATHON_PUBLIC_URL` | Base URL for verification email links (e.g. `https://your-host.com`) |
| `SLACATHON_SMTP_HOST` | SMTP server hostname |
| `SLACATHON_SMTP_FROM` | Sender address for outgoing emails |

Vault paths:
- dev: `secret/ad/ad-accel-online-ml-dev/slacathon26/secret`
- prod: `secret/ad/ad-accel-online-ml-prod/slacathon26/secret`

## Ingress Hostnames

Set in overlay patches:
- `kubernetes/overlays/dev/ingress-patch.yaml` → `ad-accel-online-ml-dev.slac.stanford.edu`
- `kubernetes/overlays/prod/ingress-patch.yaml` → `ard-modeling-service.slac.stanford.edu`

Update these values before the first Argo CD sync.

## Single-Worker Constraint

`SLACATHON_WORKERS` must remain 1. SQLite cannot handle concurrent writers. The Kubernetes Deployment is also constrained to `replicas: 1` with `strategy: Recreate`.
