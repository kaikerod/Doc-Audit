import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DocAudit")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    api_v1_prefix: str = "/api/v1"
    upload_dir: str = os.getenv("UPLOAD_DIR", "storage/uploads")
    upload_max_size_bytes: int = int(os.getenv("UPLOAD_MAX_SIZE_BYTES", str(5 * 1024 * 1024)))
    upload_max_files: int = int(os.getenv("UPLOAD_MAX_FILES", "20"))
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://docaudit:docaudit@db:5432/docaudit"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    openrouter_api_url: str = os.getenv(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
    openrouter_timeout_seconds: float = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
    openrouter_timeout_retries: int = int(os.getenv("OPENROUTER_TIMEOUT_RETRIES", "2"))


settings = Settings()
