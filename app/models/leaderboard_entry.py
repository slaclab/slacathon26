from typing import Optional
from sqlmodel import SQLModel, Field


class LeaderboardEntry(SQLModel, table=True):
    __tablename__ = "leaderboardentry"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    display_name: str
    input_json: str
    score: float
    solved: bool
    timestamp: float
