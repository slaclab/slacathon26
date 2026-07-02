# Phase 02 — DB Engine & User Model

## Scope
Create `app/db.py` (SQLite engine, session factory, dev seeding) and `app/models/user.py` (User table).
No routes touched. No existing code modified. App still boots identically.

## Prereq
Phase 01 merged (settings fields exist).

## Files Created
| File | Purpose |
|---|---|
| `app/db.py` | Engine, `get_session` dependency, `create_db_and_tables()`, `seed_dev_users()` |
| `app/models/user.py` | `User` SQLModel table |

---

## `app/models/user.py`

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[str] = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True
    )
    email: str = Field(unique=True, index=True)
    display_name: str
    api_key: str = Field(unique=True, index=True)
    verified: bool = Field(default=False)
    verify_token: str = Field(unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)
```

---

## `app/db.py`

```python
import logging
from sqlmodel import Session, SQLModel, create_engine, select
from app.settings import settings

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///./data/users.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    logger.info("DB tables created/verified")
    with Session(engine) as session:
        seed_dev_users(session)


def get_session():
    with Session(engine) as session:
        yield session


def seed_dev_users(session: Session):
    from app.models.user import User

    dev_users = [
        ("key_123", "Alex", "alex@dev.local"),
        ("key_456", "Chris", "chris@dev.local"),
        ("key_789", "Ken", "ken@dev.local"),
    ]
    for api_key, display_name, email in dev_users:
        existing = session.exec(select(User).where(User.api_key == api_key)).first()
        if not existing:
            session.add(User(
                email=email,
                display_name=display_name,
                api_key=api_key,
                verified=True,
                verify_token=f"dev-seeded-{api_key}",
            ))
    session.commit()
    logger.info("Dev users seeded")
```

**Only seeds when invoked explicitly** — not wired to `app/main.py` yet (that's Phase 06).

---

## Acceptance Criteria
- `python -c "from app.db import create_db_and_tables; create_db_and_tables()"` creates `data/users.db`
- `User` model importable with no errors
- `get_session` yields a valid `Session`
- Dev seed inserts 3 rows; second call is idempotent (no duplicates)

---

## Test Suite: `tests/test_phase02_db.py`

```python
"""Phase 02 — DB engine, User model, seeding."""
import pytest
from sqlmodel import Session, create_engine, SQLModel, select


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    from app.models.user import User  # noqa: F401 — registers metadata
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_user_create(session):
    from app.models.user import User
    u = User(
        email="a@b.com",
        display_name="Alice",
        api_key="testkey1",
        verified=False,
        verify_token="tok1",
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    assert u.id is not None
    assert u.verified is False


def test_user_unique_email(session):
    from app.models.user import User
    from sqlalchemy.exc import IntegrityError
    session.add(User(email="dup@b.com", display_name="D1", api_key="k_dup1", verified=True, verify_token="tv1"))
    session.commit()
    session.add(User(email="dup@b.com", display_name="D2", api_key="k_dup2", verified=True, verify_token="tv2"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_user_unique_api_key(session):
    from app.models.user import User
    from sqlalchemy.exc import IntegrityError
    session.add(User(email="e1@b.com", display_name="E1", api_key="same_key", verified=True, verify_token="tv3"))
    session.commit()
    session.add(User(email="e2@b.com", display_name="E2", api_key="same_key", verified=True, verify_token="tv4"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_seed_dev_users(engine):
    from app.db import seed_dev_users
    from app.models.user import User
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed_dev_users(s)
        users = s.exec(select(User)).all()
        keys = {u.api_key for u in users}
        assert "key_123" in keys
        assert "key_456" in keys
        assert "key_789" in keys
        # idempotent
        seed_dev_users(s)
        users2 = s.exec(select(User)).all()
        assert len(users2) == len(users)


def test_get_session_yields():
    from app.db import get_session
    # get_session is a generator-based dependency; just verify it yields
    gen = get_session()
    s = next(gen)
    assert s is not None
    try:
        next(gen)
    except StopIteration:
        pass
```
