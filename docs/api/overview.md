# API Overview

## Base URL

All routes are mounted under the `root_path` prefix (default `/slacathon26`).

| Environment | Base URL |
|---|---|
| Local dev | `http://localhost:8000/slacathon26` |
| Dev cluster | `https://ad-accel-online-ml-dev.slac.stanford.edu/slacathon26` |
| Production | `https://ard-modeling-service.slac.stanford.edu/slacathon26` |

## Authentication

Protected endpoints require `X-API-Key: <your-key>` header. API keys are issued after email verification (see [Authentication](authentication.md)).

## Content Type

All request/response bodies are JSON (`Content-Type: application/json`).

## API Style

REST over HTTP/1.1. No versioning prefix in URLs — the app is versioned by container image tag.

## Endpoint Groups

| Group | Prefix | Auth required |
|---|---|---|
| Registration | `/register`, `/verify`, `/resend-key` | No |
| Task metadata | `/task` | No |
| Validation jobs | `/validate`, `/jobs/{id}` | Yes |
| Leaderboard submit | `/submit` | Yes |
| Leaderboard view | `/leaderboard` | No |
| History | `/history` | Yes |
| UI pages | `/`, `/board`, `/team` | No |
| Health | `/health` | No |

## See Also

- [Endpoints](endpoints.md) — full reference
- [Authentication](authentication.md) — registration + key usage
- [Error Handling](error-handling.md) — status codes and error shapes
