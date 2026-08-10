# Kubernetes

See also: [DEPLOYMENT.md](../DEPLOYMENT.md) for the full step-by-step deploy procedure.

## Structure

```
kubernetes/
├── base/                        shared resources
│   ├── namespace.yaml           namespace: slacathon26
│   ├── configmap.yaml           non-secret env vars
│   ├── vault-secret.yaml        VaultSecret CR → K8s Secret
│   ├── persistentvolumeclaim.yaml  1 Gi RWO PVC for /app/data
│   ├── service.yaml             ClusterIP, port 8000
│   ├── deployment.yaml          1 replica, Recreate strategy
│   ├── ingress.yaml             base ingress skeleton
│   └── kustomization.yaml
└── overlays/
    ├── dev/                     dev-specific patches
    └── prod/                    prod-specific patches
```

## Resources

### Namespace

`slacathon26` — all resources live in this namespace.

### Deployment

| Field | Value |
|---|---|
| Replicas | 1 (SQLite single-writer constraint) |
| Strategy | `Recreate` |
| Image | patched per overlay |
| Container port | 8000 |
| CPU request/limit | 100m / 1 |
| Memory request/limit | 256Mi / 1Gi |
| Data volume | `/app/data` from PVC |

**Probes:**

| Probe | Path | Initial delay | Period |
|---|---|---|---|
| Readiness | `/health` | 5 s | 10 s |
| Liveness | `/health` | 15 s | 20 s |

### PersistentVolumeClaim

`slacathon26-data` — `1Gi ReadWriteOnce`. The cluster must provide a default `StorageClass` that satisfies this claim.

### Service

`ClusterIP` on port 8000. An external ingress or gateway handles public traffic.

### ConfigMap (`slacathon26-config`)

| Key | Value |
|---|---|
| `SLACATHON_ACTIVE_TASK` | `flat_beam` |
| `SLACATHON_ROOT_PATH` | `/slacathon26` |
| `SLACATHON_DB_FILE` | `/app/data/slacathon.db` |
| `SLACATHON_LEADERBOARD_FILE` | `/app/data/leaderboard.json` |
| `SLACATHON_SMTP_PORT` | `587` |
| `SLACATHON_LOG_LEVEL` | `info` |

### VaultSecret → `application-secrets`

The `ricoberger.de/v1alpha1` VaultSecret controller reads from Vault and produces a K8s Secret named `application-secrets` with these keys:

- `SLACATHON_ALTCHA_HMAC_KEY`
- `SLACATHON_PUBLIC_URL`
- `SLACATHON_SMTP_HOST`
- `SLACATHON_SMTP_FROM`

Vault paths:
- dev: `secret/ad/ad-accel-online-ml-dev/slacathon26/secret`
- prod: `secret/ad/ad-accel-online-ml-prod/slacathon26/secret`

## Overlays

### dev overlay

| Patch | What it changes |
|---|---|
| `deployment-patch.yaml` | Image tag for dev |
| `ingress-patch.yaml` | Host: `ad-accel-online-ml-dev.slac.stanford.edu` |
| `secret-patch.yaml` | Vault path → `ad-accel-online-ml-dev` |

### prod overlay

| Patch | What it changes |
|---|---|
| `deployment-patch.yaml` | Image tag for prod |
| `ingress-patch.yaml` | Host: `ard-modeling-service.slac.stanford.edu` |
| `secret-patch.yaml` | Vault path → `ad-accel-online-ml-prod` |

## Argo CD

Each environment is reconciled by a separate Argo CD application:

| Environment | Argo CD source path |
|---|---|
| dev | `kubernetes/overlays/dev` |
| prod | `kubernetes/overlays/prod` |

Merging a deployment PR into `main` triggers Argo CD to sync automatically (or on the next poll cycle).

## Validate a Kustomize Build

```bash
kubectl kustomize kubernetes/overlays/dev
kubectl kustomize kubernetes/overlays/prod
```
