# CI/CD

Three GitHub Actions workflows implement the full build-deploy-promote pipeline.

## Workflow Summary

| Workflow | Trigger | Outcome |
|---|---|---|
| `release-build.yml` | PR merged → `main`, or manual | Builds and pushes Docker image to GHCR |
| `deploy-dev.yml` | Manual (`workflow_dispatch`) | Patches dev overlay, opens deployment PR |
| `promote-production.yml` | Manual (`workflow_dispatch`) | Verifies dev, waits for approval, patches prod overlay, opens PR |

## `release-build.yml` — Build deployment image

**Triggers:** PR merged into `main`, or `workflow_dispatch`.

**Steps:**
1. Check out `main` at the merge commit.
2. Capture `IMAGE_TAG = git rev-parse --short=7 HEAD`.
3. Log in to GHCR with `GITHUB_TOKEN`.
4. Build and push:
   - `ghcr.io/slaclab/slacathon26:<sha7>` (immutable)
   - `ghcr.io/slaclab/slacathon26:latest` (convenience alias)

**Permissions:** `packages: write`

**Concurrency group:** `slacathon26-release-build` (no cancel — serialized).

---

## `deploy-dev.yml` — Deploy to dev

**Trigger:** Manual. Input: `image_tag` (7-char hex SHA).

**Steps:**
1. Validate `image_tag` format.
2. `docker manifest inspect` — confirm image exists in GHCR.
3. Create branch `deploy/dev-<sha7>`.
4. `sed` patch `kubernetes/overlays/dev/deployment-patch.yaml` with new image.
5. `kubectl kustomize` dry-run.
6. Push branch, open PR against `main`.

**After merge:** Argo CD reconciles the dev cluster.

**GitHub Environment:** `dev` (optional required reviewers).

**Concurrency group:** `slacathon26-dev-deployment` (no cancel — serialized).

---

## `promote-production.yml` — Promote to production

**Trigger:** Manual. Input: `image_tag` (must already be deployed to dev).

**Jobs (sequential):**

```
verify-dev  ──────────────────►  create-production-pr
  - validate image_tag format        (environment: production)
  - docker manifest inspect          - re-check dev overlay
  - grep dev overlay for sha7        - create branch deploy/prod-<sha7>
  - kubectl kustomize dev            - patch prod overlay
                                     - push + open PR
```

**Approval gate:** `create-production-pr` job uses `environment: production`. GitHub pauses the workflow and waits for required reviewers before proceeding.

**After merge:** Argo CD reconciles the prod cluster.

**Concurrency group:** `slacathon26-production-promotion` (no cancel — serialized).

---

## Required GitHub Setup

1. GHCR package visibility: **public**
2. GitHub Environment `dev` — optional reviewers
3. GitHub Environment `production` — **required reviewers** (approval gate)
4. Branch ruleset on `main`: require PRs, allow Actions bot to push/create PRs, enable `GITHUB_TOKEN` write permission

## Secrets

All workflows use `secrets.GITHUB_TOKEN` only — no additional secrets needed.
