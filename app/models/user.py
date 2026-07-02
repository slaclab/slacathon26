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
