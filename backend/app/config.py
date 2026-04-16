import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DocAudit")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    api_v1_prefix: str = "/api/v1"
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://docaudit:docaudit@db:5432/docaudit"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


settings = Settings()
