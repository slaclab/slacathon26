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
    )

    # str (not list) so sources never attempt json-decode on comma string
    api_keys: str = Field(default="", description="Comma or space separated list of valid API keys")

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

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        return v.lower()


settings = Settings()

# Post-process: turn the raw str into list in-place so existing code `settings.api_keys` sees list (no caller changes)
if isinstance(settings.api_keys, str):
    raw = settings.api_keys
    parsed = [k.strip() for k in raw.replace(",", " ").split() if k.strip()] if raw else []
    object.__setattr__(settings, "api_keys", parsed)

# Normalize file paths to absolute using repo root (supports relative overrides in .env, works from any cwd)
for key in ('leaderboard_file', 'db_file'):
    val = getattr(settings, key)
    if val and not Path(val).is_absolute():
        object.__setattr__(settings, key, _data_file(val))
