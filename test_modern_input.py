"""Real test driving shipped modern-format code paths after legacy helper removal."""
import job_manager
import middleware
from main import app
from fastapi.testclient import TestClient

def test_load_jobs_modern():
    job_manager.load_jobs()
    assert len(job_manager.jobs) > 0
    sample = next(iter(job_manager.jobs.values()))
    assert isinstance(sample.get("input"), dict)
    assert "values" not in sample
    print("test_load_jobs_modern PASSED")

def test_get_job_modern():
    job_manager.load_jobs()
    jid = next(iter(job_manager.jobs.keys()))
    job = job_manager.get_job(jid)
    assert job is not None
    assert isinstance(job.get("input"), dict)
    print("test_get_job_modern PASSED")

def test_load_leaderboard_modern():
    entries = middleware.load_leaderboard()
    assert len(entries) > 0
    assert isinstance(entries[0].input, dict)
    print("test_load_leaderboard_modern PASSED")

def test_app_paths():
    c = TestClient(app)
    t = c.get("/task").json()
    assert t.get("name") == "Beamline Guru"
    v = c.post("/validate", json={"input": {"q1":1,"q2":-1,"q3":0,"d2":0.1,"d3":0.2}}, headers={"X-API-Key":"key_123"}).json()
    assert "job_id" in v
    jid = v["job_id"]
    j = c.get(f"/jobs/{jid}", headers={"X-API-Key":"key_123"}).json()
    assert j.get("status") in ("processing", "completed")
    lb = c.get("/leaderboard").json()
    assert "total_entries" in lb
    print("test_app_paths PASSED")

if __name__ == "__main__":
    test_load_jobs_modern()
    test_get_job_modern()
    test_load_leaderboard_modern()
    test_app_paths()
    print("ALL TESTS PASSED")
