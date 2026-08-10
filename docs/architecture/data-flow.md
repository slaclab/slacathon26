# Data Flow

## Registration Flow

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant A as FastAPI
    participant DB as SQLite
    participant SM as SMTP

    U->>A: GET /register
    A-->>U: HTML form (Jinja2)
    U->>A: POST /register {email, display_name, altcha_payload}
    A->>A: verify_captcha(altcha_payload)
    A->>DB: create_unverified_user(email, display_name, token, expires_at)
    A->>SM: send_verification_email(email, verify_url)
    A-->>U: 202 {detail: "Check your email"}

    U->>A: GET /verify?token=<tok>
    A-->>U: HTML form
    U->>A: POST /verify {token, altcha_payload}
    A->>A: verify_captcha()
    A->>DB: get_user_by_token(token)
    A->>DB: mark_user_verified(row_id, new_api_key)
    A->>SM: send_api_key_email(email, api_key)
    A-->>U: 303 → /registered
```

## Validation Job Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant DB as SQLite
    participant TP as Thread Pool
    participant T as Task Module

    C->>A: POST /validate {input: {...}}\n X-API-Key: <key>
    A->>DB: verify API key
    A->>A: validate input schema (TASK.Input)
    A->>DB: charge_quota() [atomic BEGIN IMMEDIATE]
    A->>DB: insert_job(job_record)
    A-->>C: 200 {job_id, status: "processing", quota}

    Note over A,TP: asyncio.create_task fires independently
    A->>TP: run_in_executor(TASK.validate, input_data)
    TP->>T: TASK.validate(data)
    T-->>TP: Result {score, solved, message, evaltime}
    TP->>DB: update_job(job_id, status="completed", result)

    C->>A: GET /jobs/{job_id}\n X-API-Key: <key>
    A->>DB: get_job(job_id)
    A-->>C: 200 {status, result, quota}
```

## Submit to Leaderboard Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant DB as SQLite
    participant LB as leaderboard.json

    C->>A: POST /submit {input: {...}}\n X-API-Key: <key>
    A->>DB: charge_quota() [atomic]
    A->>A: TASK.validate(input) [synchronous, in request]
    A->>LB: add_to_leaderboard(user_id, input, score, solved)
    Note over LB: dedup check → sort → trim to top-15 → os.replace atomic write
    A-->>C: 200 {score, solved, rank, leaderboard_size}
```

## Quota Enforcement

Quota is stored durably in `quota_charges` table. On every `/validate` and `/submit` call:

1. `db.charge_quota()` opens `BEGIN IMMEDIATE`.
2. Counts existing charges for `user_id`.
3. If `count >= limit` → `ROLLBACK` → raises `RuntimeError` → HTTP 429.
4. Otherwise inserts charge row → `COMMIT`.

Limit source of truth = `TASK.MAX_VALIDATIONS_PER_USER` (loaded at startup). Default fallback = `SLACATHON_MAX_VALIDATIONS_PER_USER` env var (default 10000).

## Background Cleanup

A background `asyncio` task (`_cleanup_loop`) runs every `SLACATHON_CLEANUP_INTERVAL_MINUTES` (default 10) minutes. It calls `db.delete_expired_unverified_users()`, which removes rows where `verified=0` and `expires_at < now()`.
