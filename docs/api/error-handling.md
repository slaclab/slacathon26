# Error Handling

## Error Response Format

All errors follow FastAPI's standard JSON format:

```json
{"detail": "Human-readable error description"}
```

## HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| `400` | Bad Request | Invalid CAPTCHA payload |
| `401` | Unauthorized | Missing, invalid, or unverified API key |
| `403` | Forbidden | Accessing a job that belongs to another user |
| `404` | Not Found | Job ID not found; email not registered for resend-key |
| `409` | Conflict | Email already registered and verified |
| `410` | Gone | Verification token expired (re-register) |
| `422` | Unprocessable Entity | Input validation failed (wrong fields, wrong types) |
| `429` | Too Many Requests | Per-user validation quota exceeded |
| `500` | Internal Server Error | Task execution failure or unexpected exception |
| `503` | Service Unavailable | Email service unreachable during registration |

## Quota Errors (429)

When the per-user quota is reached, the response is:

```json
{"detail": "Validation limit of 10000 reached for this API key"}
```

The quota limit comes from the active task's `MAX_VALIDATIONS_PER_USER` attribute (default 10,000). Current usage is visible in every `/validate` and `/jobs/{id}` response under `quota`.

## Input Validation Errors (422)

FastAPI returns a detailed validation error for malformed input:

```json
{
  "detail": [
    {
      "type": "extra_forbidden",
      "loc": ["body", "input", "unknown_field"],
      "msg": "Extra inputs are not permitted"
    }
  ]
}
```

The active task's `Input` model uses `model_config = {"extra": "forbid"}`, so unknown parameter names are rejected.

## Retry Guidance

- `429` — Wait or reduce submission rate; quota resets are not currently supported
- `503` — Retry after a short delay; SMTP server may be temporarily unavailable
- `500` — Report to platform administrators; the job may have stored a failure result
