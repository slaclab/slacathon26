"""Multi-task API: registry, per-task routes, leaderboard filtering."""
import time

import pytest

from slacathon import db
from slacathon.registry import discover_tasks, get_registry
from slacathon.tasks.base import make_task_id

GOOD = {"q1": 0.5, "q2": -0.5, "q3": 0.1, "d2": 0.2, "d3": 0.3}


@pytest.fixture
def api_key(client):
    key = "test-key-tasks-api"
    db.upsert_user(key, "tasks-tester")
    return key


def test_registry_discovers_all_tasks(client):
    assert {"flat_beam", "fel", "cuinj"} <= set(get_registry())
    assert "base" not in get_registry()


def test_discover_tasks_rejects_bad_module(tmp_path, monkeypatch):
    import importlib
    pkg = tmp_path / "bad_tasks"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "broken.py").write_text("X = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(RuntimeError):
        discover_tasks(importlib.import_module("bad_tasks"))


def test_list_tasks(client):
    res = client.get("/tasks")
    assert res.status_code == 200
    ids = {t["public_task_id"] for t in res.json()["tasks"]}
    assert {"flat_beam", "fel", "cuinj"} <= ids


def test_task_metadata(client):
    res = client.get("/tasks/fel")
    assert res.status_code == 200
    assert res.json()["name"] == "FEL Pulse Intensity"


@pytest.mark.parametrize("method,path", [
    ("get", "/tasks/nope"),
    ("post", "/tasks/nope/submit"),
    ("get", "/leaderboard?public_task_id=nope"),
])
def test_unknown_task_404(client, api_key, method, path):
    kwargs = {"headers": {"X-API-Key": api_key}}
    if method == "post":
        kwargs["json"] = {"input": GOOD}
    assert getattr(client, method)(path, **kwargs).status_code == 404


def test_validate_route_removed(client, api_key):
    res = client.post("/tasks/flat_beam/validate", json={"input": GOOD}, headers={"X-API-Key": api_key})
    assert res.status_code in (404, 405)


def test_submit_bad_input_422(client, api_key):
    before = client.get("/leaderboard?public_task_id=flat_beam").json()["total_entries"]
    res = client.post("/tasks/flat_beam/submit", json={"input": {"q1": 99.0}}, headers={"X-API-Key": api_key})
    assert res.status_code == 422
    assert res.json()["detail"][0] == {
        "loc": ["input", "q1"], "msg": "Value 99.0 outside bounds [-10.0, 10.0]", "type": "value_error.bounds",
    }
    assert client.get("/leaderboard?public_task_id=flat_beam").json()["total_entries"] == before


def _wait(client, api_key, job_id):
    deadline = time.time() + 10
    while True:
        job = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key}).json()
        if job["status"] == "completed" or time.time() > deadline:
            return job
        time.sleep(0.2)


def test_submit_job_ranks_and_filters_leaderboard(client, api_key):
    res = client.post("/tasks/flat_beam/submit", json={"input": GOOD}, headers={"X-API-Key": api_key})
    assert res.status_code == 200
    assert res.json()["public_task_id"] == "flat_beam"
    assert res.json()["status"] == "processing"

    job = _wait(client, api_key, res.json()["job_id"])
    assert job["status"] == "completed"
    assert job["public_task_id"] == "flat_beam"
    assert "score" in job["result"]
    assert job["result"]["rank"] is not None

    filtered = client.get("/leaderboard?public_task_id=flat_beam").json()
    assert filtered["total_entries"] >= 1
    assert all(e["public_task_id"] == "flat_beam" for e in filtered["leaderboard"])
    assert client.get("/leaderboard?public_task_id=fel").json()["leaderboard"] == []

    everything = client.get("/leaderboard").json()
    assert any(e["public_task_id"] == "flat_beam" for e in everything["leaderboard"])
    assert {"flat_beam", "fel", "cuinj"} <= set(everything["tasks"])


def test_tasks_persisted_with_internal_id(client, tmp_db):
    problem = get_registry()["flat_beam"]
    assert problem.task_id == make_task_id("flat_beam") != "flat_beam"
    db.sync_tasks([(problem.task_id, "flat_beam", problem.TASK_NAME)])
    conn = db._connect()
    try:
        row = conn.execute("SELECT public_task_id FROM tasks WHERE task_id = ?", (problem.task_id,)).fetchone()
    finally:
        conn.close()
    assert row["public_task_id"] == "flat_beam"


def test_sync_tasks_rekeys_legacy_alias_rows(client):
    db.insert_leaderboard_entry("legacy-user", "cuinj", {"x": 1}, 1.0, False, time.time())
    db.sync_tasks([(make_task_id("cuinj"), "cuinj", "Injector Emittance")])
    assert db.get_all_leaderboard_entries("cuinj") == []
    assert any(e["user_id"] == "legacy-user" for e in db.get_all_leaderboard_entries(make_task_id("cuinj")))
