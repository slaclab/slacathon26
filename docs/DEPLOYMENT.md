# Deployment Guide

GitOps deployment via GitHub Actions + Kustomize + Argo CD.

## Overview

```
PR merged → main
    ↓
release-build.yml         builds & pushes ghcr.io/slaclab/slacathon26:<sha7>
    ↓  (manual trigger)
deploy-dev.yml            patches dev overlay → opens PR → merge → Argo CD syncs dev cluster
    ↓  (manual trigger, same sha7)
promote-production.yml    verifies dev overlay → approval gate → patches prod overlay → opens PR → merge → Argo CD syncs prod cluster
```

## Workflows

### 1. `release-build.yml` — Build & publish image

**Trigger:** PR merged into `main`, or manual `workflow_dispatch`.

**What it does:**
1. Checks out `main` post-merge.
2. Captures the 7-character commit SHA as `IMAGE_TAG`.
3. Logs in to GHCR with `GITHUB_TOKEN`.
4. Builds and pushes two tags:
   - `ghcr.io/slaclab/slacathon26:<sha7>` — immutable, used by all deployment workflows
   - `ghcr.io/slaclab/slacathon26:latest` — convenience alias only; never used by deployments

**Permissions required:** `packages: write`

---

### 2. `deploy-dev.yml` — Deploy to dev

**Trigger:** Manual `workflow_dispatch` with input `image_tag` (7-char hex SHA).

**What it does:**
1. Validates `image_tag` format (`[0-9a-f]{7}`).
2. Verifies the image exists in GHCR (`docker manifest inspect`).
3. Creates branch `deploy/dev-<sha7>`.
4. Patches `kubernetes/overlays/dev/deployment-patch.yaml` with the new image reference.
5. Validates the overlay with `kubectl kustomize`.
6. Pushes the branch and opens a PR against `main`.

**Merge the PR** → Argo CD reconciles the dev cluster.

**Concurrency group:** `slacathon26-dev-deployment` (no cancel-in-progress — serialised).

---

### 3. `promote-production.yml` — Promote to production

**Trigger:** Manual `workflow_dispatch` with input `image_tag` (must already be in dev overlay).

**Jobs (sequential):**

| Job | What it does |
|---|---|
| `verify-dev` | Confirms the image tag is present in `kubernetes/overlays/dev/deployment-patch.yaml` and the overlay builds cleanly. |
| `create-production-pr` | Waits for approval through the `production` GitHub Environment, re-checks dev overlay after approval, patches prod overlay, pushes branch `deploy/prod-<sha7>`, opens PR. |

**Merge the PR** → Argo CD reconciles the production cluster.

**Approval gate:** the `production` GitHub Environment must have required reviewers configured.

---

## Kubernetes Layout

```
kubernetes/
├── base/                        shared resources (all environments)
│   ├── namespace.yaml
│   ├── configmap.yaml           non-secret env vars (active task, paths, SMTP port)
│   ├── vault-secret.yaml        VaultSecret CR → K8s Secret "application-secrets"
│   ├── persistentvolumeclaim.yaml  1 Gi RWO for SQLite + leaderboard JSON
│   ├── service.yaml             ClusterIP on port 8000
│   ├── deployment.yaml          1 replica, Recreate strategy
│   ├── ingress.yaml
│   └── kustomization.yaml
└── overlays/
    ├── dev/
    │   ├── deployment-patch.yaml   image tag for dev
    │   ├── ingress-patch.yaml      host: ad-accel-online-ml-dev.slac.stanford.edu
    │   ├── secret-patch.yaml       Vault path: .../ad-accel-online-ml-dev/...
    │   └── kustomization.yaml
    └── prod/
        ├── deployment-patch.yaml   image tag for prod
        ├── ingress-patch.yaml      host: ard-modeling-service.slac.stanford.edu
        ├── secret-patch.yaml       Vault path: .../ad-accel-online-ml-prod/...
        └── kustomization.yaml
```

### Deployment constraints

- **Replicas:** 1 only. SQLite and `leaderboard.json` share a single PVC; concurrent writers are unsafe.
- **Strategy:** `Recreate` — old pod terminates before new one starts.
- **Resources:** requests `100m CPU / 256Mi`; limits `1 CPU / 1Gi`.
- **Probes:** readiness at `/health` (5 s delay, 10 s period); liveness at `/health` (15 s delay, 20 s period).
- **Service type:** `ClusterIP` — an external ingress/gateway handles public routing.

### ConfigMap (base)

| Key | Default | Purpose |
|---|---|---|
| `SLACATHON_ACTIVE_TASK` | `flat_beam` | Active challenge task |
| `SLACATHON_ROOT_PATH` | `/slacathon26` | FastAPI root path |
| `SLACATHON_DB_FILE` | `/app/data/slacathon.db` | SQLite path on PVC |
| `SLACATHON_LEADERBOARD_FILE` | `/app/data/leaderboard.json` | Leaderboard JSON on PVC |
| `SLACATHON_SMTP_PORT` | `587` | SMTP port |
| `SLACATHON_LOG_LEVEL` | `info` | Log verbosity |

### Secrets (Vault → K8s Secret `application-secrets`)

Managed by the `ricoberger.de/v1alpha1` VaultSecret controller. The controller reads from Vault and creates the K8s Secret; no secret values are committed to Git.

| Vault key | Purpose |
|---|---|
| `SLACATHON_ALTCHA_HMAC_KEY` | CAPTCHA signing key |
| `SLACATHON_PUBLIC_URL` | Base URL for email verification links |
| `SLACATHON_SMTP_HOST` | SMTP server hostname |
| `SLACATHON_SMTP_FROM` | Sender address for outgoing email |

**Vault paths:**
- dev: `secret/ad/ad-accel-online-ml-dev/slacathon26/secret`
- prod: `secret/ad/ad-accel-online-ml-prod/slacathon26/secret`

---

## First-time Setup

1. Set the `slacathon26` GHCR package visibility to **public**.
2. Create GitHub Environments `dev` and `production`. Add required reviewers to `production`.
3. Configure a branch ruleset on `main`: require PRs, allow GitHub Actions bot to push branches and open PRs, enable `GITHUB_TOKEN` workflow write permission.
4. Replace ingress hostnames in `kubernetes/overlays/dev/ingress-patch.yaml` and `kubernetes/overlays/prod/ingress-patch.yaml`.
5. Install the `ricoberger.de/v1alpha1` VaultSecret controller in each cluster and configure Vault auth.
6. Populate both Vault paths with the four required secret keys (see table above).
7. Configure two Argo CD Applications:
   - dev cluster → `kubernetes/overlays/dev`
   - prod cluster → `kubernetes/overlays/prod`
8. Each cluster needs a default `StorageClass` that can satisfy a `1Gi ReadWriteOnce` claim.

---

## Step-by-step Deploy

```bash
# 1. merge your PR into main — release-build.yml fires automatically
#    note the 7-char SHA from the Actions run (e.g. a1b2c3d)

# 2. deploy to dev
#    GitHub Actions → "Deploy image to dev" → Run workflow → image_tag: a1b2c3d
#    review + merge the opened PR

# 3. promote to production (after dev validation)
#    GitHub Actions → "Promote image to production" → Run workflow → image_tag: a1b2c3d
#    approve the production Environment gate
#    review + merge the opened PR
```

---

## Rollback

Re-run `deploy-dev.yml` or `promote-production.yml` with the previous known-good SHA. The workflow creates a new deployment branch and PR; merging it reverts the overlay to the old image.
