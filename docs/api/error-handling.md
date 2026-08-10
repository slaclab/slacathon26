# Error Handling

## Error Response Shape

FastAPI returns errors as JSON:

```json
{"detail": "Human-readable message"}
```

Validation errors (422) use FastAPI's default schema:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "q1"],
      "msg": "Field required"
    }
  ]
}
```

## Status Code Reference

| Code | Meaning | Common causes |
|---|---|---|
| 200 | OK | Successful request |
| 202 | Accepted | Registration submitted |
| 303 | See Other | Verification complete, redirect to `/registered` |
| 401 | Unauthorized | Missing or invalid `X-API-Key` |
| 403 | Forbidden | Job belongs to a different user |
| 404 | Not Found | Job ID or token not found |
| 409 | Conflict | Email already registered and verified |
| 410 | Gone | Verification token expired |
| 422 | Unprocessable Entity | Input schema validation failure |
| 429 | Too Many Requests | Per-user validation quota exhausted |
| 500 | Internal Server Error | Unexpected server-side failure |
| 503 | Service Unavailable | SMTP server unreachable during registration |

## Quota Errors

When `POST /validate` or `POST /submit` hits the per-user limit:

```json
{"detail": "Validation limit of 10000 reached for this API key"}
```

The current quota state is included in every `/validate` and `/jobs/{id}` response:

```json
"quota": {"used": 10000, "limit": 10000, "remaining": 0}
```

## Task / External Service Errors

`fel` and `cuinj` tasks call the SLAC ARD modeling service. If that service is unreachable, `validate()` returns a `Result` with `score=1e10` and an error message — the HTTP request itself still returns 200. This prevents client errors from masking network issues.
