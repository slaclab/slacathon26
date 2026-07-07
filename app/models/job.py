import uuid
import time
from typing import Optional
from sqlmodel import SQLModel, Field


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(index=True)
    input_json: str
    status: str = Field(default="processing")
    result_json: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
