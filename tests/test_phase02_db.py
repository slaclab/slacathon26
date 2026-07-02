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
    gen = get_session()
    s = next(gen)
    assert s is not None
    try:
        next(gen)
    except StopIteration:
        pass
