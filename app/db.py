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
