# API Overview

## Base URL

All endpoints are served under the `root_path` configured via `SLACATHON_ROOT_PATH` (default `/slacathon26`):

```
http://<host>:<port>/slacathon26/<endpoint>
```

## Authentication

Protected endpoints require the `X-API-Key` header:

```
X-API-Key: your_api_key_here
```

API keys are obtained by [registering](../getting-started/quickstart.md) via the web form. Dev seed keys (`key_123`, `key_456`, `key_789`) are available on a fresh database.

See [Authentication](authentication.md) for full details.

## Endpoint Groups

| Group | Endpoints | Auth |
|-------|-----------|------|
| Public pages | `GET /`, `/board`, `/team`, `/health` | None |
| Task info | `GET /leaderboard`, `GET /task` | None |
| Registration | `GET/POST /register`, `GET/POST /verify`, `GET/POST /resend-key` | None (CAPTCHA) |
| Validation | `POST /validate`, `GET /jobs/{id}` | X-API-Key |
| Leaderboard | `POST /submit`, `GET /history` | X-API-Key |

## Response Format

All JSON responses use standard HTTP status codes. Errors follow FastAPI's default format:

```json
{"detail": "Error description here"}
```

See [Error Handling](error-handling.md) for the full error code reference.

## Rate Limiting

There is no HTTP-level rate limiting. Per-user quotas are enforced at the application level via `MAX_VALIDATIONS_PER_USER` (defined by the active task, default 10,000). The quota is returned in every `/validate` and `/jobs/{id}` response:

```json
"quota": {"used": 5, "limit": 10000, "remaining": 9995}
```
