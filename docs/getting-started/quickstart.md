# Quickstart

Get from zero to a leaderboard submission in five steps.

## Prerequisites

- Python ≥ 3.10, Docker (for Mailpit)
- Repo cloned and installed: `pip install -e .`

## Step 1 — Start the server and mail catcher

```bash
docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit:latest
PYTHONPATH=src uvicorn slacathon.main:app --host 127.0.0.1 --port 8000 --reload
```

## Step 2 — Register

```bash
curl -s http://localhost:8000/slacathon26/register
# → open http://localhost:8000/slacathon26/register in a browser
# Fill in email + display name + solve CAPTCHA → submit
```

Open `http://localhost:8025`, click the verification link, solve CAPTCHA. A second email delivers your API key.

## Step 3 — Check the task

```bash
curl -s http://localhost:8000/slacathon26/task | python -m json.tool
```

Note `parameter_labels`, `bounds`, `target`, and `minimize`.

## Step 4 — Validate a parameter set

```bash
API_KEY="your-api-key-here"

JOB=$(curl -s -X POST http://localhost:8000/slacathon26/validate \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"q1": 0, "q2": 0, "q3": 0, "d2": 0, "d3": 0}}')
echo $JOB

JOB_ID=$(echo $JOB | python -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Poll until completed
curl -s http://localhost:8000/slacathon26/jobs/$JOB_ID \
  -H "X-API-Key: $API_KEY" | python -m json.tool
```

## Step 5 — Submit best result to leaderboard

```bash
curl -s -X POST http://localhost:8000/slacathon26/submit \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"q1": 0, "q2": 0, "q3": 0, "d2": 0, "d3": 0}}' \
  | python -m json.tool

# View the leaderboard
open http://localhost:8000/slacathon26/board
```

## Next: use an optimizer client

The `clients/` directory provides ready-made Bayesian optimizers:

```bash
pip install numpy scipy scikit-learn
# Edit clients/usage.py and set API_KEY
python clients/usage.py
```

See [Guides / Optimizer Clients](../guides/optimizer-clients.md) for details.
