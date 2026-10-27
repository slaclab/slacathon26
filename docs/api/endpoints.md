# API Endpoints

All paths are relative to the base URL (e.g. `http://localhost:8000/slacathon26`).

---

## Public — no auth

### `GET /health`

Liveness probe. Used by Kubernetes readiness/liveness probes.

**Response 200**
```json
{"status": "rockin' and rollin'"}
```

---

### `GET /tasks`

Lists every problem served by the platform. `public_task_id` is the readable alias used in URLs (the task's `PUBLIC_ID`, else its module name). Internally each task also has a `task_id` (UUID5 of the alias) stored in the `tasks` table and used by jobs and leaderboard rows.

**Response 200**
```json
{"tasks": [{"public_task_id": "flat_beam", "name": "Beamline Guru", ...}, {"task_id": "fel", ...}]}
```

---

### `GET /tasks/{public_task_id}`

Returns one problem's configuration: input schema, parameter labels, bounds, scoring direction. `404` for unknown `public_task_id`.

**Response 200**
```json
{
  "public_task_id": "flat_beam",
  "name": "Beamline Guru",
  "input_schema": { ... },
  "result_schema": { ... },
  "parameter_labels": ["q1", "q2", "q3", "d2", "d3"],
  "bounds": [[-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0]],
  "target": 0.0,
  "minimize": true,
  "failure_score": 1e10,
  "max_concurrency": 1,
  "max_validations_per_user": 10000
}
```

---

### `GET /leaderboard?public_task_id=<id>`

Top entries per problem. With `public_task_id`, only that problem (`404` if unknown); without, all problems concatenated, each sorted by its own direction. `tasks` maps every `public_task_id` to its name/target/minimize.

**Response 200**
```json
{
  "total_entries": 1,
  "leaderboard": [
    {
      "public_task_id": "flat_beam",
      "user": "Alice",
      "input": {"q1": 1.2, "q2": -0.5, "q3": 0.8, "d2": 0.3, "d3": 0.1},
      "score": 0.00002,
      "solved": false,
      "timestamp": 1720000000.0
    }
  ],
  "tasks": {"flat_beam": {"name": "Beamline Guru", "target": 0.0, "minimize": true}}
}
```

---

### `GET /captcha-challenge`

Returns an Altcha proof-of-work challenge. Required by registration forms.

---

## Registration

### `GET /register`

Returns the HTML registration form.

### `POST /register`

Submit registration request. Sends a verification email.

**Request body**
```json
{
  "email": "user@example.com",
  "display_name": "Alice",
  "altcha_payload": "<solved captcha string>"
}
```

**Response 202**
```json
{"detail": "Check your email — verification link sent"}
```

**Errors**

| Status | Condition |
|---|---|
| 409 | Email already registered and verified |
| 422 | Invalid email or missing fields |
| 503 | SMTP server unreachable |

---

### `GET /verify?token=<token>`

Returns the email verification HTML form.

### `POST /verify`

Complete email verification. On success, sends an API key email and redirects to `/registered`.

**Request body**
```json
{
  "token": "<token from email link>",
  "altcha_payload": "<solved captcha string>"
}
```

**Response** — `303` redirect to `/registered`.

**Errors**

| Status | Condition |
|---|---|
| 404 | Token not found |
| 410 | Token expired (re-register) |

---

### `GET /resend-key`

Returns the API key resend HTML form.

### `POST /resend-key`

Resend API key to a verified email address.

**Request body**
```json
{
  "email": "user@example.com",
  "altcha_payload": "<solved captcha string>"
}
```

**Response 200**
```json
{"detail": "API key sent — check your inbox"}
```

---

## Protected — `X-API-Key` required

### `POST /tasks/{public_task_id}/submit`

Submit parameter inputs to one problem. The input is checked against the problem schema and bounds first; on success a background job evaluates it and records the score on that problem's leaderboard. Returns a `job_id` immediately; poll `GET /jobs/{job_id}` for score and rank.

**Request body** — flat dict or wrapped:
```json
{"input": {"q1": 1.5, "q2": -2.0, "q3": 0.5, "d2": 1.0, "d3": 0.8}}
```

**Response 200**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "public_task_id": "flat_beam",
  "status": "processing",
  "message": "Submission recorded. ...",
  "quota": {"used": 42, "limit": 10000, "remaining": 9958}
}
```

**Errors**

| Status | Condition |
|---|---|
| 401 | Missing or invalid `X-API-Key` |
| 404 | Unknown `public_task_id` |
| 422 | Input fails schema or bounds check; `detail` is `[{"loc": ["input", "q1"], "msg": "...", "type": "value_error.bounds"}]` |
| 429 | Quota exhausted |

---

### `GET /jobs/{job_id}`

Poll for job result.

**Response 200 — processing**
```json
{
  "job_id": "...",
  "public_task_id": "flat_beam",
  "status": "processing",
  "created_at": 1720000000.0,
  "input": {"q1": 1.5, ...},
  "quota": {"used": 42, "limit": 10000, "remaining": 9958}
}
```

**Response 200 — completed**
```json
{
  "job_id": "...",
  "public_task_id": "flat_beam",
  "status": "completed",
  "created_at": 1720000000.0,
  "completed_at": 1720000002.1,
  "input": {"q1": 1.5, ...},
  "result": {
    "score": 0.000012,
    "solved": false,
    "message": "Objective is 0.000012, expected minimal (less than 1e-4)",
    "evaltime": 0.002,
    "rank": 3,
    "leaderboard_size": 3
  },
  "quota": {"used": 42, "limit": 10000, "remaining": 9958}
}
```

**Errors**

| Status | Condition |
|---|---|
| 403 | Job belongs to a different user |
| 404 | Job not found |

---

### `GET /history`

Returns the last `max_queries_per_user` (default 10) submitted input vectors for the authenticated user (in-memory, resets on restart).

**Response 200**
```json
{
  "user": "Alice",
  "total_submissions": 5,
  "history": [
    {"q1": 1.5, "q2": -2.0, "q3": 0.5, "d2": 1.0, "d3": 0.8}
  ]
}
```
