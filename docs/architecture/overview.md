# Architecture Overview

SLACathon is a single-process FastAPI web service that hosts pluggable beam-physics optimization challenges. Participants submit parameter vectors via a REST API and receive scores from a task-specific objective function.

## Component Map

```mermaid
graph TD
    Browser["Browser / Client Script"]
    API["FastAPI app\n(slacathon/main.py)"]
    Auth["API Key Auth\n(middleware.py)"]
    JobMgr["Job Manager\n(job_manager.py)"]
    Task["Active Task Module\n(tasks/*.py)"]
    DB["SQLite file (default)\nor rqlite cluster"]
    LB["Leaderboard JSON\n(data/leaderboard.json)"]
    ExSvc["External Model Service\n(SLAC ARD)"]
    Email["SMTP / Mailpit"]

    Browser -->|"X-API-Key header"| API
    API --> Auth
    Auth --> DB
    API --> JobMgr
    JobMgr --> DB
    JobMgr -->|"asyncio thread pool"| Task
    Task -->|"flat_beam (local)"| DB
    Task -->|"fel / cuinj"| ExSvc
    API --> LB
    API --> Email
```

## Layers

| Layer | Module(s) | Responsibility |
|---|---|---|
| HTTP routing | `main.py` | Route definitions, request parsing, response shaping |
| Auth | `middleware.py` | API key validation against SQLite; leaderboard read/write |
| Job pipeline | `job_manager.py` | Job creation, background execution, quota enforcement |
| Task protocol | `tasks/base.py`, `tasks/*.py` | Objective function, input schema, scoring constants |
| Persistence | `db.py` | CRUD for users, jobs, quota_charges, leaderboard; backend `sqlite` (file) or `rqlite` (HTTP, pyrqlite) |
| Configuration | `settings.py` | `pydantic-settings` with `SLACATHON_` prefix |
| Registration | `main.py` + `captcha.py` + `email_service.py` | Self-serve signup with CAPTCHA + email verification |

## Key Design Decisions

**Single replica, `Recreate` strategy.** With the sqlite backend the file on the PVC allows one writer, and `job_manager`/`middleware` keep per-process caches and locks, so the Deployment runs one pod. The rqlite backend removes the storage coupling (see `docs/todo/rqlite-backend.md`); horizontal scaling additionally needs the in-process caches removed.

**Async HTTP + sync task execution.** FastAPI is async; task `validate()` functions are synchronous (potentially CPU-bound). Jobs are dispatched via `asyncio.get_running_loop().run_in_executor(None, ...)` so they run in a thread pool without blocking the event loop.

**Atomic quota enforcement.** `db.charge_quota()` is a single conditional `INSERT ... SELECT ... WHERE count < limit` statement, so check and insert are atomic on both backends without an explicit transaction (pyrqlite cannot express `BEGIN`/`COMMIT`). A per-call `charge_token` tells the caller whether its row was inserted.

**Pluggable tasks.** Tasks are plain Python modules discovered by `task_loader.py` at startup. Switching tasks requires only an environment variable change (`SLACATHON_ACTIVE_TASK`).

**Leaderboard as flat JSON.** The top-15 leaderboard is intentionally simple plain JSON, written atomically via `os.replace()`. Jobs and users live in SQLite.

## See Also

- [Data Flow](data-flow.md) — request lifecycle end-to-end
- [Guides / Writing a Task](../guides/writing-a-task.md) — task protocol specification
