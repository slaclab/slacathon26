from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SLACATHON_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # str (not List) so sources never attempt json-decode on comma string
    api_keys: str = Field(default="", description="Comma or space separated list of valid API keys")

    # Task configuration
    active_task: str = Field(default="flat_beam", description="Active task module name")

    # Server settings
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8888)
    workers: int = Field(default=1)
    timeout: int = Field(default=300)
    log_level: str = Field(default="info")

    # File paths
    leaderboard_file: str = Field(default="data/leaderboard.json")
    user_names_file: str = Field(default="data/user_names.json")
    jobs_file: str = Field(default="data/jobs.json")

    # Limits
    max_queries_per_user: int = Field(default=10)
    max_validations_per_user: int = Field(default=10000)
    leaderboard_size: int = Field(default=15)

    # Failure handling (fallback, tasks can override via FAILURE_SCORE)
    failure_score: float = Field(default=1.0e10)

    # FastAPI
    root_path: str = Field(default="/slacathon26")

    # SMTP
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=1025)
    smtp_from: str = Field(default="noreply@slacathon26.local")

    # Public URL (base for verify links in emails)
    public_url: str = Field(default="http://localhost:8000")

    # Registration
    verify_timeout_hours: int = Field(default=24)
    cleanup_interval_minutes: int = Field(default=10)

    # Altcha (self-hosted proof-of-work CAPTCHA — no external service)
    altcha_hmac_key: str = Field(default="dev-hmac-key-change-in-prod")

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
