from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

def _data_file(name: str) -> str:
    # Resolve relative to repo root (src/slacathon/settings.py -> parents[2])
    root = Path(__file__).resolve().parents[2]
    p = Path(name)
    if not p.is_absolute():
        p = root / p
    return str(p)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SLACATHON_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Task configuration
    active_task: str = Field(default="flat_beam", description="Active task module name")

    # Server settings
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8888)
    workers: int = Field(default=1)
    timeout: int = Field(default=300)
    log_level: str = Field(default="info")

    # File paths (resolved relative to repo root for cwd-independence; .env can override with relative or absolute)
    leaderboard_file: str = Field(default_factory=lambda: _data_file("data/leaderboard.json"))
    db_file: str = Field(default_factory=lambda: _data_file("data/slacathon.db"))

    # Limits
    max_queries_per_user: int = Field(default=10)
    max_validations_per_user: int = Field(default=10000)
    leaderboard_size: int = Field(default=15)

    # Failure handling (fallback, tasks can override via FAILURE_SCORE)
    failure_score: float = Field(default=1.0e10)

    # FastAPI
    root_path: str = Field(default="/slacathon26")

    # Registration / email
    public_url: str = Field(default="http://localhost:8000")
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=1025)
    smtp_use_tls: bool = Field(default=False)
    smtp_username: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    smtp_from: str = Field(default="noreply@slacathon26.local")
    smtp_validate_certs: bool = Field(default=True)
    altcha_hmac_key: str = Field(default="dev-hmac-key-change-in-prod")
    verify_timeout_hours: int = Field(default=24)
    cleanup_interval_minutes: int = Field(default=10)

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        return v.lower()


settings = Settings()

# Normalize file paths to absolute using repo root (supports relative overrides in .env, works from any cwd)
for key in ('leaderboard_file', 'db_file'):
    val = getattr(settings, key)
    if val and not Path(val).is_absolute():
        object.__setattr__(settings, key, _data_file(val))
