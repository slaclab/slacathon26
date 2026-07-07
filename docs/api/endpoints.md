# API Endpoints

## Public Endpoints

### `GET /task`

Returns the active task's schema, bounds, and scoring configuration.

**Response:**
```json
{
  "name": "Beamline Guru",
  "input_schema": { ... },
  "result_schema": { ... },
  "parameter_labels": ["q1", "q2", "q3", "d2", "d3"],
  "bounds": [[-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0]],
  "target": 0.0,
  "minimize": true,
  "failure_score": 10000000000.0,
  "max_validations_per_user": 10000
}
```

### `GET /leaderboard`

Returns the top N leaderboard entries, sorted by score (ascending for minimize tasks).

**Response:**
```json
{
  "total_entries": 3,
  "leaderboard": [
    {"user": "Alice", "input": {...}, "score": 0.000042, "solved": false, "timestamp": 1720000000.0},
    {"user": "Bob",   "input": {...}, "score": 0.262394, "solved": false, "timestamp": 1720000001.0}
  ]
}
```

### `GET /health`

```json
{"status": "rockin' and rollin'"}
```

---

## Registration Endpoints

All registration endpoints require an Altcha CAPTCHA payload. See [Authentication](authentication.md#captcha).

### `POST /register`

Create a new unverified user and send a verification email.

**Request:**
```json
{
  "email": "user@example.com",
  "display_name": "MyHandle",
  "altcha_payload": "<base64-encoded-solution>"
}
```

**Response (202):**
```json
{"detail": "Check your email — verification link sent"}
```

**Errors:**
- `400` — Invalid CAPTCHA
- `409` — Email already registered and verified
- `503` — Email service unavailable

### `POST /verify`

Verify email address with the token from the verification email.

**Request:**
```json
{
  "token": "<token-from-email>",
  "altcha_payload": "<base64-encoded-solution>"
}
```

**Response:** `303 Redirect → /registered`

**Errors:**
- `400` — Invalid CAPTCHA
- `404` — Invalid or expired token
- `410` — Token expired (registration deleted; re-register)

### `POST /resend-key`

Resend the API key to a verified email address.

**Request:**
```json
{
  "email": "user@example.com",
  "altcha_payload": "<base64-encoded-solution>"
}
```

**Response (200):**
```json
{"detail": "API key sent — check your inbox"}
```

**Errors:**
- `400` — Invalid CAPTCHA
- `404` — No verified account found for that email

---

## Protected Endpoints

All require `X-API-Key` header. Return `401` if key is missing, invalid, or belongs to an unverified user.

### `POST /validate`

Submit a parameter set for asynchronous scoring. Returns immediately with a job ID.

**Request:**
```json
{"input": {"q1": 2.25, "q2": -2.22, "q3": 0.96, "d2": 0.033, "d3": 1.413}}
```

**Response (200):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Submission recorded. Poll GET /jobs/{job_id} to retrieve the result.",
  "quota": {"used": 1, "limit": 10000, "remaining": 9999}
}
```

**Errors:**
- `401` — Invalid API key
- `422` — Input validation failed (unknown fields, wrong types)
- `429` — Validation quota exceeded
- `500` — Task execution error

### `GET /jobs/{job_id}`

Poll for a job result. Ownership is enforced (API key must match the submitting user).

**Response (job still running):**
```json
{
  "job_id": "550e...",
  "status": "processing",
  "created_at": 1720000000.0,
  "input": {"q1": 2.25, ...},
  "quota": {"used": 1, "limit": 10000, "remaining": 9999}
}
```

**Response (job completed):**
```json
{
  "job_id": "550e...",
  "status": "completed",
  "created_at": 1720000000.0,
  "completed_at": 1720000002.0,
  "input": {"q1": 2.25, ...},
  "result": {
    "score": 1.589,
    "solved": false,
    "message": "Objective is 1.589, expected minimal (less than 1e-4)",
    "evaltime": 0.001
  },
  "quota": {"used": 1, "limit": 10000, "remaining": 9999}
}
```

**Errors:**
- `403` — Job belongs to another user
- `404` — Job not found

### `POST /submit`

Submit a parameter set directly to the leaderboard (synchronous evaluation).

**Request:**
```json
{"input": {"q1": 2.25, "q2": -2.22, "q3": 0.96, "d2": 0.033, "d3": 1.413}}
```

**Response (200):**
```json
{
  "submitted": true,
  "user": "Alice",
  "score": 1.589,
  "solved": false,
  "message": "Objective is 1.589, expected minimal (less than 1e-4)",
  "rank": 3,
  "leaderboard_size": 5
}
```

Note: `rank` is `null` if the submission is a duplicate (identical input already on the leaderboard).

**Errors:**
- `429` — Quota exceeded
- `500` — Task execution error

### `GET /history`

Returns the user's last N validation submissions (inputs only, newest first).

**Response:**
```json
{
  "user": "Alice",
  "total_submissions": 2,
  "history": [
    {"q1": 2.55, "q2": -2.52, "q3": 1.09, "d2": 0.033, "d3": 1.413},
    {"q1": 2.25, "q2": -2.22, "q3": 0.96, "d2": 0.033, "d3": 1.413}
  ]
}
```

The `total_submissions` count reflects only the last `max_queries_per_user` (default 10) records returned; it is not a lifetime total.
