import os
from dataclasses import dataclass, field


def _parse_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name, "")
    if not raw_value.strip():
        return default

    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DocAudit")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    api_v1_prefix: str = "/api/v1"
    upload_dir: str = os.getenv("UPLOAD_DIR", "storage/uploads")
    upload_max_size_bytes: int = int(os.getenv("UPLOAD_MAX_SIZE_BYTES", str(5 * 1024 * 1024)))
    upload_max_files: int = int(os.getenv("UPLOAD_MAX_FILES", "20"))
    # SQLite keeps direct local runs lightweight; Docker overrides this with Postgres.
    database_url: str = os.getenv("DATABASE_URL", "sqlite+pysqlite:///./docaudit.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2.5:free")
    openrouter_api_url: str = os.getenv(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
    openrouter_referer: str = os.getenv("OPENROUTER_REFERER", "")
    openrouter_title: str = os.getenv("OPENROUTER_TITLE", os.getenv("APP_NAME", "DocAudit"))
    openrouter_timeout_seconds: float = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
    openrouter_timeout_retries: int = int(os.getenv("OPENROUTER_TIMEOUT_RETRIES", "2"))
    cors_allow_origins: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv_env(
            "CORS_ALLOW_ORIGINS",
            (
                "null",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "http://localhost:5500",
                "http://127.0.0.1:5500",
            ),
        )
    )
    cors_allow_origin_regex: str = os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    )


settings = Settings()
