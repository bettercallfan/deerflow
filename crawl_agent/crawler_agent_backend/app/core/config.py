from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Crawler Agent Service"
    app_version: str = "0.1.0"
    debug: bool = False

    api_prefix: str = "/api/v1"
    timezone: str = "Asia/Shanghai"

    metadata_database_url: str = Field(
        default="sqlite:///./crawler_agent_meta.db",
        description="SQLAlchemy database URL for metadata storage",
    )

    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = 10

    max_concurrent_runs: int = 2

    # Optional default storage connection hints
    default_mysql_url: str | None = None
    default_milvus_uri: str | None = None
    default_milvus_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
