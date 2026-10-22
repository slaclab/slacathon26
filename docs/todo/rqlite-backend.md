# rqlite Database Backend

## Context

All persistent state (users, jobs, quota charges, leaderboard) lives in a single SQLite file managed by
`src/slacathon/db.py` (stdlib `sqlite3`, synchronous, module-level functions, per-process `threading.RLock`).
In Kubernetes the file sits on a `ReadWriteOnce` PVC mounted into the single app pod.

Consequences today:

- The database lives and dies with the pod/PVC; no replication, no backups.
- `strategy: Recreate` is forced (two pods cannot share the PVC), so every rollout has downtime.
- The app can never run more than one replica.

Goal: add **[rqlite](https://rqlite.io)** (Raft-replicated SQLite with an HTTP API) as an alternative
storage backend, selected by `SLACATHON_DB_BACKEND=sqlite|rqlite` (default `sqlite`).

- Local development and the pytest suite keep using the embedded SQLite file.
- Kubernetes runs a 3-node rqlite StatefulSet in the same namespace, with rqlite's built-in automatic
  backups to S3-compatible storage.

### Client: pyrqlite

[pyrqlite](https://github.com/rqlite/pyrqlite) is a DB-API 2.0 driver. Verified behaviour relevant to us:

- `pyrqlite.dbapi2.connect(scheme="http", host, port=4001, user, password, timeout, max_redirects)`.
- `qmark` parameters; `cursor.lastrowid` and `cursor.rowcount` populated from the rqlite response;
  `executemany` supported (sent as one transactional `/db/execute` request).
- Rows are `tuple` + `Mapping`, so `row["col"]`, `row[0]`, `dict(row)` and `.keys()` behave like
  `sqlite3.Row`. No row adapter needed.
- `commit()` / `rollback()` are no-ops. Every `execute` is its own HTTP request and its own transaction.
  **No `BEGIN`/`COMMIT`, no `executescript`, no multi-statement atomicity across Python calls.**
- `PRAGMA xxx = y` statements are not usable, but the table-valued function
  `SELECT name FROM pragma_table_info('t')` works through `/db/query`.
- Consistency level is a per-call kwarg `execute(sql, params, level=...)`; the rqlite default (`weak`,
  served by the leader) is adequate.
- Errors raise `pyrqlite.exceptions.Error`, not `sqlite3.IntegrityError`.

rqlite 8.x embeds a recent SQLite, so `UPSERT ... ON CONFLICT DO UPDATE`, `INSERT OR REPLACE`,
`AUTOINCREMENT`, `CHECK`, `strftime`, and subquery-in-`DELETE` are all available.

### Compatibility with `docs/todo/admin-ui.md`

The admin UI plan adds an `is_admin INTEGER DEFAULT 0` column via the idempotent-ALTER pattern plus four
simple db functions (`DELETE ... rowcount`, `UPDATE`, two `SELECT`s). All of these are portable; the only
adjustment is to append its ALTER to the `_MIGRATIONS` list introduced below.

---

## Changes

### 1. `src/slacathon/settings.py`

Add fields (env prefix `SLACATHON_`); keep `db_file` for the sqlite backend:

```python
db_backend: str = Field(default="sqlite", description="Storage backend: sqlite | rqlite")
rqlite_scheme: str = Field(default="http")
rqlite_host: str = Field(default="localhost")
rqlite_port: int = Field(default=4001)
rqlite_user: str = Field(default="")
rqlite_password: str = Field(default="")      # from Vault in Kubernetes
rqlite_timeout: float = Field(default=10.0)   # seconds per HTTP request
```

Add a validator rejecting any `db_backend` outside `{"sqlite", "rqlite"}`.

---

### 2. `src/slacathon/db.py`

The public module-level function API stays unchanged. Callers in `main.py`, `job_manager.py`,
`middleware.py` and `scripts/` are untouched.

#### 2a. Connection factory and backend flag

```python
DB_PATH: str = settings.db_file
DB_BACKEND: str = settings.db_backend   # patchable in tests, like DB_PATH
_lock = threading.RLock()


def _is_rqlite() -> bool:
    return DB_BACKEND == "rqlite"


def _locked():
    """Serialize writers only for the embedded sqlite backend; Raft serializes rqlite."""
    return _lock if not _is_rqlite() else contextlib.nullcontext()


def _connect():
    if _is_rqlite():
        from pyrqlite import dbapi2 as rq   # lazy: optional for local dev
        return rq.connect(
            scheme=settings.rqlite_scheme,
            host=settings.rqlite_host,
            port=settings.rqlite_port,
            user=settings.rqlite_user or None,
            password=settings.rqlite_password or None,
            timeout=settings.rqlite_timeout,
        )
    _ensure_parent_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

Replace every `with _lock:` (about 20 sites) with `with _locked():`. `conn.commit()` and `conn.close()`
calls stay as they are (no-ops / harmless on pyrqlite).

#### 2b. `init_db()`: no `executescript`, no PRAGMAs, portable DDL

- Run the four `PRAGMA` statements only when `not _is_rqlite()`.
- Replace `executescript("""...""")` with a `_SCHEMA: list[str]` of individual
  `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` statements executed in a loop.
- Change `created_at REAL DEFAULT (strftime('%s','now'))` to plain `created_at REAL` and set
  `time.time()` app-side in every INSERT into `users` (`upsert_user`, `create_unverified_user`).
  Existing rows keep their values.
- Replace the blanket try/except ALTER loop with column introspection so real failures are no longer
  masked. Note: the two existing `ADD COLUMN ... UNIQUE` statements (`email`, `verify_token`) are
  rejected by SQLite itself and have always failed silently. Drop `UNIQUE` from them and enforce
  uniqueness with explicit indexes instead.

```python
_MIGRATIONS = [  # (table, column, statement)
    ("users", "email",        "ALTER TABLE users ADD COLUMN email TEXT"),
    ("users", "verified",     "ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 0"),
    ("users", "verify_token", "ALTER TABLE users ADD COLUMN verify_token TEXT"),
    ("users", "expires_at",   "ALTER TABLE users ADD COLUMN expires_at REAL"),
    ("leaderboard", "task_name", "ALTER TABLE leaderboard ADD COLUMN task_name TEXT NOT NULL DEFAULT ''"),
    # admin-ui.md: ("users", "is_admin", "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"),
]

_UNIQUE_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_verify_token ON users(verify_token)",
]


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"SELECT name FROM pragma_table_info('{table}')").fetchall()
    return {r["name"] for r in rows}
```

Loop: `if column not in _columns(conn, table): conn.execute(stmt)`. Keep a narrow try/except around the
ALTER only, for the race where two processes initialize at the same time.

#### 2c. `charge_quota()`: single-statement atomic check + insert

The current `BEGIN IMMEDIATE` / `SELECT COUNT` / `INSERT` / `COMMIT` sequence cannot be expressed with
pyrqlite. Replace it with one conditional insert, which is atomic on both backends:

```python
cur = conn.execute(
    """
    INSERT INTO quota_charges (user_id, charged_at, job_id, kind)
    SELECT ?, ?, ?, ?
    WHERE (SELECT COUNT(*) FROM quota_charges WHERE user_id = ?) < ?
    """,
    (user_id, charged_at, job_id, kind, user_id, limit),
)
conn.commit()
if cur.rowcount == 0:
    raise RuntimeError(f"Validation limit of {limit} reached for this API key")
row = conn.execute(
    "SELECT COUNT(*) AS c FROM quota_charges WHERE user_id = ?", (user_id,)
).fetchone()
return int(row["c"])
```

On sqlite `_locked()` still serializes callers; on rqlite the Raft log serializes writes, so the
statement is atomic cluster-wide. If pyrqlite's `rowcount` turns out not to be populated for
`INSERT ... SELECT`, fall back to checking `cur.lastrowid`. The integration test (section 7) covers this.

#### 2d. Remaining SQL audit

Portable as-is: UPSERT `ON CONFLICT(api_key) DO UPDATE` (`upsert_user`), `INSERT OR REPLACE`
(`insert_job`), `cur.lastrowid` (`insert_leaderboard_entry`), `cur.rowcount`
(`delete_expired_unverified_users`), `DELETE ... WHERE id NOT IN (SELECT ... LIMIT ?)`
(`trim_leaderboard`), dynamic `SET` clause (`update_job`).

Error handling: build a per-backend `_DB_ERRORS` tuple (`sqlite3.Error` vs `pyrqlite.exceptions.Error`)
and use it wherever `sqlite3.*Error` is caught. UNIQUE violations on rqlite must be detected from the
error message (`"UNIQUE constraint failed"`).

#### 2e. Logging

`init_db()` logs `Database initialized (backend=sqlite path=...)` or
`(backend=rqlite host=...:port)`.

---

### 3. `pyproject.toml`

- Add `pyrqlite` to `dependencies` (pure Python, no transitive deps; the lazy import keeps it harmless).
- Register the pytest marker `rqlite` under `[tool.pytest.ini_options]`.

---

### 4. `src/slacathon/job_manager.py`, `src/slacathon/middleware.py` (document only)

Both assume a single process: `job_manager` keeps an in-memory `jobs` dict guarded by `jobs_lock`;
`middleware._leaderboard_lock` serializes exists → insert → trim → read; `get_valid_api_keys()` does a
full-table read on every authenticated request.

With rqlite every DB call is an HTTP round trip (a few ms in-cluster), so those per-request reads become
the dominant cost.

- **Phase 1 (this TODO):** keep the app at `replicas: 1`. Decoupling the DB from the pod already removes
  the PVC and allows `RollingUpdate`.
- **Phase 2 (separate TODO, `docs/todo/horizontal-scaling.md`):** drop the in-memory jobs cache, move
  leaderboard dedup/trim to single atomic statements, add a short TTL cache for API keys, then raise
  replicas.

---

### 5. Kubernetes (`kubernetes/base/`)

#### 5a. `rqlite-statefulset.yaml` (new)

Adapted from the upstream `statefulset-3-node.yaml`:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: rqlite
spec:
  serviceName: rqlite-headless
  replicas: 3
  podManagementPolicy: Parallel
  selector:
    matchLabels: {app: rqlite}
  template:
    metadata:
      labels: {app: rqlite}
    spec:
      terminationGracePeriodSeconds: 10
      containers:
        - name: rqlite
          image: rqlite/rqlite:8.43.0   # pin; check latest 8.x at implementation time
          args:
            - -disco-mode=dns
            - '-disco-config={"name":"rqlite-headless"}'
            - -bootstrap-expect=3
            - -join-interval=1s
            - -join-attempts=120
            - -auth=/rqlite/auth/auth.json
            - -join-as=app
            - -auto-backup=/rqlite/backup/backup.json
            # - -auto-restore=/rqlite/backup/restore.json   # disaster recovery only
          ports:
            - {containerPort: 4001, name: rqlite}
            - {containerPort: 4002, name: raft}
          readinessProbe:
            httpGet: {path: /readyz, port: 4001}
            initialDelaySeconds: 2
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet: {path: /readyz?noleader, port: 4001}
            initialDelaySeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          resources:
            requests: {cpu: 100m, memory: 128Mi}
            limits: {cpu: 500m, memory: 512Mi}
          volumeMounts:
            - {name: rqlite-data, mountPath: /rqlite/file}
            - {name: rqlite-auth, mountPath: /rqlite/auth, readOnly: true}
            - {name: rqlite-backup, mountPath: /rqlite/backup, readOnly: true}
      volumes:
        - name: rqlite-auth
          secret:
            secretName: rqlite-secrets
            items: [{key: auth.json, path: auth.json}]
        - name: rqlite-backup
          secret:
            secretName: rqlite-secrets
            items: [{key: backup.json, path: backup.json}]
  volumeClaimTemplates:
    - metadata: {name: rqlite-data}
      spec:
        accessModes: [ReadWriteOnce]
        resources: {requests: {storage: 2Gi}}
        # storageClassName: same as persistentvolumeclaim.yaml
```

Also in this file: a `PodDisruptionBudget` with `minAvailable: 2` (node drains never lose quorum) and a
preferred `podAntiAffinity` across nodes. `/readyz` needs the `ready` permission; grant `ready` and
`status` to the anonymous user `*` in `auth.json` so probes run unauthenticated.

#### 5b. `rqlite-service.yaml` (new)

- `rqlite-headless`: `clusterIP: None`, `publishNotReadyAddresses: true` (**required**, otherwise DNS
  discovery deadlocks during bootstrap), ports 4001 and 4002.
- `rqlite`: regular ClusterIP on 4001. The app connects to `rqlite:4001`; pyrqlite follows leader
  redirects.

#### 5c. `rqlite-vault-secret.yaml` (new) and Vault contents

A `VaultSecret` (`ricoberger.de/v1alpha1`) producing Secret `rqlite-secrets` with keys `auth.json`,
`backup.json`. Values live only in Vault, separate dev and prod paths. Shapes (placeholders only):

`auth.json`

```json
[
  {"username": "app",   "password": "<pw>", "perms": ["execute", "query", "join", "load", "backup", "status", "ready"]},
  {"username": "admin", "password": "<pw>", "perms": ["all"]},
  {"username": "*",     "perms": ["ready", "status"]}
]
```

`backup.json` (rqlite auto-backup: leader-only, uploads only when data changed)

```json
{
  "version": 1,
  "type": "s3",
  "interval": "1h",
  "vacuum": true,
  "timestamp": true,
  "sub": {
    "access_key_id": "<key>",
    "secret_access_key": "<secret>",
    "region": "us-east-1",
    "bucket": "slacathon26-backups",
    "path": "rqlite/slacathon26.sqlite.gz",
    "endpoint": "https://<s3-compatible-endpoint>",
    "force_path_style": true
  }
}
```

`timestamp: true` keeps a history of objects rather than overwriting one key.

**Fallback without S3:** `rqlite-backup-cronjob.yaml` (`curlimages/curl`) calling
`GET http://rqlite:4001/db/backup?fmt=sql&compress` on a schedule and writing to a small backup PVC.

**Restore:** either `-auto-restore` pointing at the same `sub` block (applies only when the cluster is
empty on first boot), or manually `POST /boot` with a SQLite file into a fresh single node and scale up.

#### 5d. App-side manifests

- `configmap.yaml`: add `SLACATHON_DB_BACKEND=rqlite`, `SLACATHON_RQLITE_HOST=rqlite`,
  `SLACATHON_RQLITE_PORT=4001`, `SLACATHON_RQLITE_USER=app`; drop `SLACATHON_DB_FILE` and the stale
  `SLACATHON_LEADERBOARD_FILE`.
- `vault-secret.yaml`: add key `SLACATHON_RQLITE_PASSWORD` to `application-secrets`.
- `deployment.yaml`: remove the `slacathon26-data` volume and mount, switch to `RollingUpdate`, add an
  init container that waits for `http://rqlite:4001/readyz`.
- `persistentvolumeclaim.yaml`: keep until cutover is verified; remove in the cleanup PR.
- `kustomization.yaml`: register the new resources.
- `overlays/dev`, `overlays/prod`: patch the Vault path for `rqlite-secrets`. Dev may patch the
  StatefulSet to `replicas: 1` and `-bootstrap-expect=1` to save resources.

Validate with `kubectl kustomize kubernetes/overlays/dev` and `kubectl kustomize kubernetes/overlays/prod`.

---

### 6. Data migration and cutover

Default path uses rqlite's native SQLite loading; no custom script.

1. Deploy the rqlite StatefulSet while the app still runs on sqlite. Wait until `/status` shows 3 nodes
   and a leader.
2. Scale the app to 0 to stop writes. Copy `/app/data/slacathon.db` out of the PVC with a debug pod
   (run `PRAGMA wal_checkpoint(TRUNCATE)` first, or copy the `-wal` file as well).
3. Port-forward `rqlite-0:4001` and load the file:
   ```bash
   curl -u admin:<pw> -XPOST localhost:4001/db/load \
     -H "Content-type: application/octet-stream" --data-binary @slacathon.db
   ```
   `/db/load` replicates through Raft on a running cluster. Verify `SELECT COUNT(*)` per table matches.
4. Apply the new ConfigMap and Deployment and scale the app to 1. `init_db()` finds the tables and the
   migrations are no-ops.
5. Smoke test registration, validation and leaderboard. Keep the old PVC for one week, then delete.

Fallback `scripts/migrate_sqlite_to_rqlite.py`: iterate the four tables with `sqlite3` and insert through
pyrqlite `executemany` in 500-row batches. Model on `scripts/migrate_to_sqlite.py`.

---

### 7. Tests

- `tests/conftest.py`: default stays the sqlite temp file. Explicitly set `db.DB_BACKEND = "sqlite"` so a
  developer `.env` pointing at rqlite cannot leak into unit tests. Add a backend-agnostic helper:
  ```python
  def db_rows(sql, params=()):
      conn = db._connect()
      try:
          return [dict(r) for r in conn.execute(sql, params).fetchall()]
      finally:
          conn.close()
  ```
- `tests/test_registration.py`: replace the seven direct `sqlite3.connect(tmp_db)` blocks with db-module
  functions (`get_user_by_email`, `get_user_by_token`, ...) or the `db_rows` helper.
- `tests/test_db_portable.py` (new): `charge_quota` returns count below the limit and raises at the
  limit; `init_db()` called twice is idempotent; `_columns()` reports every expected column.
- `tests/test_rqlite_integration.py` (new): marked `@pytest.mark.rqlite`, skipped unless
  `SLACATHON_RQLITE_HOST` is set. Runs the db functions against a live rqlite: registration flow,
  `charge_quota` under 20 concurrent threads rejecting the (limit+1)th call, leaderboard insert/trim,
  UPSERT, `lastrowid`.
- CI: optional job with `services: rqlite: {image: rqlite/rqlite:8.x, ports: ["4001:4001"]}` and
  `SLACATHON_RQLITE_HOST=localhost`.
- `docker-compose.yml`: add an `rqlite` service under `profiles: [rqlite]` so the default
  `docker compose up` is unchanged.

---

### 8. Documentation

- `README.md`: backend option and new env vars.
- `docs/architecture/overview.md`, `docs/architecture/data-flow.md`: storage layer is sqlite locally and
  an rqlite cluster in Kubernetes; consistency and atomicity notes; `charge_quota` no longer uses
  `BEGIN IMMEDIATE`.
- `docs/development/local-setup.md`: running against a local rqlite (`docker compose --profile rqlite up`
  or `rqlited -node-id 1 ~/node.1`).
- `docs/deployment/*`: StatefulSet, Vault keys, backup/restore runbook, cutover steps, scaling note.
- `docs/todo/admin-ui.md`: change "idempotent ALTER, same pattern" to "append to `_MIGRATIONS`".

---

### 9. Risks and open questions

- **Consistency:** pyrqlite exposes `level` only per call; default `weak` (leader-served) is fine.
  Writes are always linearizable.
- **Latency:** each call is an HTTP round trip plus Raft commit (~2-10 ms) versus ~50 µs for sqlite.
  Per-request full-table reads in `middleware` will dominate; acceptable at hackathon scale, fixed in
  Phase 2.
- **Atomicity:** single-statement only. `charge_quota` is fixed here; audit any future multi-step write.
  pyrqlite `executemany` sends one transactional request if multi-row atomicity is ever needed.
- **Exceptions:** `pyrqlite.exceptions.Error` vs `sqlite3.*Error`; UNIQUE detection by message on rqlite.
- **`rowcount` on `INSERT ... SELECT`** through pyrqlite: verify in the integration test; fallback on
  `lastrowid`.
- **DNS discovery** requires `publishNotReadyAddresses: true` on the headless Service.
- **Backups:** confirm an S3-compatible endpoint and credentials are available; otherwise use the
  CronJob fallback.
- **Dev resources:** three rqlite pods in dev may be excessive; use the 1-node overlay patch.

---

### 10. Phased rollout (one PR each)

1. **App code:** settings fields, `db.py` refactor (`_SCHEMA`, `_MIGRATIONS` + `_columns()`,
   `charge_quota` rewrite, `_locked()`, lazy pyrqlite), `pyproject.toml`, test refactor, portable unit
   tests. Default backend stays sqlite: zero behaviour change in production.
2. **Integration test + tooling:** `test_rqlite_integration.py`, docker-compose profile, CI job. Fix any
   pyrqlite surprises.
3. **Kubernetes cluster:** StatefulSet, Services, PDB, VaultSecret, backup config, overlays. Deployed
   alongside the unchanged app. Verify cluster health and that backups land in S3.
4. **Cutover (dev, then prod):** ConfigMap/Deployment switch, `/db/load`, docs. Keep the old PVC.
5. **Cleanup:** remove the app PVC manifest and `SLACATHON_LEADERBOARD_FILE`, update `admin-ui.md`
   wording, open `docs/todo/horizontal-scaling.md`.

---

## Files Modified

| File | Change |
|------|--------|
| `src/slacathon/settings.py` | `db_backend`, `rqlite_*` fields + validator |
| `src/slacathon/db.py` | dual-backend `_connect()`, `_is_rqlite()`, `_locked()`, `_SCHEMA` list, `_MIGRATIONS` + `_columns()`, PRAGMAs sqlite-only, app-side `created_at`, single-statement `charge_quota`, `_DB_ERRORS` |
| `pyproject.toml` | add `pyrqlite`; pytest marker `rqlite` |
| `tests/conftest.py` | force `DB_BACKEND="sqlite"`, `db_rows` helper |
| `tests/test_registration.py` | remove direct `sqlite3.connect` usage |
| `tests/test_db_portable.py` | new: `charge_quota` + migration idempotency |
| `tests/test_rqlite_integration.py` | new: live rqlite suite, skipped by default |
| `docker-compose.yml` | optional `rqlite` service (profile) |
| `kubernetes/base/rqlite-statefulset.yaml` | new: 3-node StatefulSet + PDB |
| `kubernetes/base/rqlite-service.yaml` | new: headless + ClusterIP |
| `kubernetes/base/rqlite-vault-secret.yaml` | new: `auth.json`, `backup.json` |
| `kubernetes/base/rqlite-backup-cronjob.yaml` | optional: fallback when no S3 |
| `kubernetes/base/configmap.yaml` | backend/rqlite env, drop `DB_FILE`, `LEADERBOARD_FILE` |
| `kubernetes/base/vault-secret.yaml` | add `SLACATHON_RQLITE_PASSWORD` |
| `kubernetes/base/deployment.yaml` | drop PVC mount, `RollingUpdate`, wait-for-rqlite init container |
| `kubernetes/base/kustomization.yaml` | register new resources; later drop PVC |
| `kubernetes/overlays/{dev,prod}/` | Vault path patch for `rqlite-secrets`; dev 1-node patch |
| `scripts/migrate_sqlite_to_rqlite.py` | optional fallback row copier |
| `README.md`, `docs/architecture/*`, `docs/development/local-setup.md`, `docs/deployment/*`, `docs/todo/admin-ui.md` | storage/backend/runbook updates |

---

## Verification

1. `pytest` passes with the default sqlite backend (no behaviour change).
2. `docker compose --profile rqlite up -d rqlite && SLACATHON_RQLITE_HOST=localhost pytest -m rqlite`
   passes; `charge_quota` rejects the (limit+1)th of 20 concurrent calls; `insert_leaderboard_entry`
   returns a non-zero id.
3. `SLACATHON_DB_BACKEND=rqlite uvicorn slacathon.main:app` locally: register, verify email, run a
   validation, view the leaderboard. `init_db()` twice raises nothing;
   `SELECT name FROM pragma_table_info('users')` lists every column.
4. `kubectl kustomize kubernetes/overlays/dev | kubectl apply --dry-run=server -f -` (same for prod).
   After deploy, `curl rqlite:4001/status?pretty` shows 3 nodes and one leader; deleting the leader pod
   yields a new leader within seconds while the app keeps serving.
5. Backups: an object appears in the bucket after the interval (use `"interval": "5m"` in dev). Restore
   drill: fresh single-node rqlite with `-auto-restore` reports matching row counts.
6. Cutover: rqlite row counts equal those of the copied sqlite file; app log shows
   `backend=rqlite`; `kubectl rollout restart deployment` completes with no downtime.
