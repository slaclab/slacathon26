# Quickstart

Get from zero to a scored submission in under 5 minutes.

## 1. Start the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 2. Check the task schema

```bash
curl http://localhost:8000/slacathon26/task
```

Response:
```json
{
  "name": "Beamline Guru",
  "parameter_labels": ["q1", "q2", "q3", "d2", "d3"],
  "bounds": [[-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0], [-10.0, 10.0]],
  "target": 0.0,
  "minimize": true
}
```

## 3. Submit a validation job

The dev server seeds three API keys: `key_123`, `key_456`, `key_789`.

```bash
curl -X POST http://localhost:8000/slacathon26/validate \
  -H "X-API-Key: key_123" \
  -H "Content-Type: application/json" \
  -d '{"input": {"q1": 2.25, "q2": -2.22, "q3": 0.96, "d2": 0.033, "d3": 1.413}}'
```

Response:
```json
{"job_id": "abc-123", "status": "processing", "quota": {"used": 1, "limit": 10000, "remaining": 9999}}
```

## 4. Poll for the result

```bash
curl http://localhost:8000/slacathon26/jobs/abc-123 \
  -H "X-API-Key: key_123"
```

When `status` is `"completed"`:
```json
{
  "status": "completed",
  "result": {
    "score": 1.589,
    "solved": false,
    "message": "Objective is 1.589, expected minimal (less than 1e-4)",
    "evaltime": 0.001
  }
}
```

## 5. Submit to the leaderboard

```bash
curl -X POST http://localhost:8000/slacathon26/submit \
  -H "X-API-Key: key_123" \
  -H "Content-Type: application/json" \
  -d '{"input": {"q1": 2.25, "q2": -2.22, "q3": 0.96, "d2": 0.033, "d3": 1.413}}'
```

## Next Steps

- See [examples/GP-optimizer.ipynb](../../examples/GP-optimizer.ipynb) for a Gaussian Process optimizer
- See [API Reference](../api/overview.md) for all endpoints
- See [Task Development Guide](../guides/task-development.md) to add a new challenge
