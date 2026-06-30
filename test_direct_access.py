#!/usr/bin/env python
"""Driving test for direct modern input access after the legacy normalization removal.
Drives only shipped code (job_manager, middleware, main). Never reimplements legacy.
Place in backend/ and run from there: python test_direct_access.py
"""
import json
import os

from fastapi.testclient import TestClient
import job_manager
import middleware
from main import app

print("=== test_direct_access: drive shipped load/get/leaderboard paths ===")

# ensure fresh load using real load_jobs (direct access now)
job_manager.load_jobs()
print("jobs count after load_jobs:", len(job_manager.jobs))

# pick a real persisted job_id dynamically from the ndjson (no hard-coded value)
real_jid = None
jobs_file = job_manager.JOBS_FILE
if os.path.exists(jobs_file):
    with open(jobs_file) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
                if rec.get("job_id"):
                    real_jid = rec["job_id"]
                    break
            except Exception:
                continue

print("real_jid_found:", bool(real_jid))

# exercise get_job on real id
got = job_manager.get_job(real_jid) if real_jid else None
assert got is not None, "get_job must return record for real persisted id"
inp = got.get("input")
assert isinstance(inp, dict), f"get_job must yield direct input dict, got {type(inp)}"
assert "values" not in got, "no legacy values key after direct load"
print("get_job on real id: direct input dict OK, no values key")

# leaderboard via shipped middleware
entries = middleware.load_leaderboard()
assert entries, "must load some leaderboard entries"
e0 = entries[0]
assert isinstance(e0.input, dict), f"LeaderboardEntry.input must be dict, got {type(e0.input)}"
print("load_leaderboard: entries use direct input dict OK")

# app paths via TestClient drive create + retrieve + lb (all emit/read modern)
c = TestClient(app)
task = c.get("/task").json()
assert task.get("name"), "task endpoint works"
print("TestClient /task OK")

# post validate uses create_job which writes "input" directly
vresp = c.post("/validate", json={"input": {"q1": 0.5, "q2": -0.5, "q3": 0.0, "d2": 0.1, "d3": 0.2}}, headers={"X-API-Key": "key_123"}).json()
jid = vresp.get("job_id")
assert jid, "validate must return job_id"
print("TestClient /validate created jid:", (jid or "")[:8], "...")

# poll the job
j = c.get(f"/jobs/{jid}", headers={"X-API-Key": "key_123"}).json()
assert "status" in j, "job fetch works"
assert "input" in j and isinstance(j.get("input"), dict), "real /jobs API must return modern input dict"
print("TestClient /jobs/{id} modern input path OK")

lb = c.get("/leaderboard").json()
assert "total_entries" in lb or isinstance(lb, list) or (isinstance(lb, dict) and "leaderboard" in lb), "leaderboard endpoint works"
print("TestClient /leaderboard OK")

print("SUCCESS_DIRECT_ACCESS")
