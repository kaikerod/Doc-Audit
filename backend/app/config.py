import os
from math import ceil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine.url import make_url

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./docaudit.db"
DOCKER_DATABASE_HOST = "db"
HOST_DATABASE_HOST = "127.0.0.1"
DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _strip_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_dotenv_file(dotenv_path: Path = DOTENV_PATH) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key or normalized_key in os.environ:
            continue

        os.environ[normalized_key] = _strip_env_value(raw_value)


_load_dotenv_file()


def _parse_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name, "")
    if not raw_value.strip():
        return default

    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


def _parse_unique_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    values = _parse_csv_env(name, default)
    unique_values = tuple(dict.fromkeys(values))
    return unique_values or default


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    return float(raw_value)


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    return int(raw_value)


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    return raw_value in {"1", "true", "yes", "on"}


def _coerce_positive_float(value: float, *, minimum: float = 0.1) -> float:
    return max(minimum, value)


def _coerce_positive_int(value: int, *, minimum: int = 1) -> int:
    return max(minimum, value)


def _is_running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def _normalize_database_url(database_url: str) -> str:
    normalized_url = database_url.strip()
    if not normalized_url or _is_running_in_container():
        return normalized_url or DEFAULT_DATABASE_URL

    try:
        parsed_url = make_url(normalized_url)
    except Exception:
        return normalized_url

    if parsed_url.host != DOCKER_DATABASE_HOST:
        return normalized_url

    # The checked-in env template is used by Docker Compose, where `db` is resolvable.
    # When the API starts directly on the host, switch to the published Postgres port.
    return parsed_url.set(host=HOST_DATABASE_HOST).render_as_string(hide_password=False)


LEGACY_OPENROUTER_TIMEOUT_SECONDS = _coerce_positive_float(
    _parse_float_env("OPENROUTER_TIMEOUT_SECONDS", 30.0)
)
DEFAULT_OPENROUTER_CONNECT_TIMEOUT_SECONDS = min(5.0, LEGACY_OPENROUTER_TIMEOUT_SECONDS)
DEFAULT_OPENROUTER_WRITE_TIMEOUT_SECONDS = min(10.0, LEGACY_OPENROUTER_TIMEOUT_SECONDS)
DEFAULT_OPENROUTER_READ_TIMEOUT_SECONDS = LEGACY_OPENROUTER_TIMEOUT_SECONDS
DEFAULT_OPENROUTER_POOL_TIMEOUT_SECONDS = min(5.0, LEGACY_OPENROUTER_TIMEOUT_SECONDS)


def _parse_positive_float_env(name: str, default: float) -> float:
    return _coerce_positive_float(_parse_float_env(name, default))


def _parse_positive_int_env(name: str, default: int) -> int:
    return _coerce_positive_int(_parse_int_env(name, default))


def _default_celery_task_soft_time_limit_seconds() -> int:
    request_budget_seconds = (
        _parse_positive_float_env(
            "OPENROUTER_CONNECT_TIMEOUT_SECONDS",
            DEFAULT_OPENROUTER_CONNECT_TIMEOUT_SECONDS,
        )
        + _parse_positive_float_env(
            "OPENROUTER_WRITE_TIMEOUT_SECONDS",
            DEFAULT_OPENROUTER_WRITE_TIMEOUT_SECONDS,
        )
        + _parse_positive_float_env(
            "OPENROUTER_READ_TIMEOUT_SECONDS",
            DEFAULT_OPENROUTER_READ_TIMEOUT_SECONDS,
        )
        + _parse_positive_float_env(
            "OPENROUTER_POOL_TIMEOUT_SECONDS",
            DEFAULT_OPENROUTER_POOL_TIMEOUT_SECONDS,
        )
    )
    default_soft_limit = max(1, int(ceil(request_budget_seconds + 5.0)))
    return max(1, _parse_int_env("CELERY_TASK_SOFT_TIME_LIMIT_SECONDS", default_soft_limit))


def _default_celery_task_time_limit_seconds() -> int:
    soft_limit_seconds = _default_celery_task_soft_time_limit_seconds()
    configured_time_limit = _parse_int_env(
        "CELERY_TASK_TIME_LIMIT_SECONDS",
        soft_limit_seconds + 5,
    )
    return max(soft_limit_seconds + 1, configured_time_limit)


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "DocAudit")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    api_v1_prefix: str = "/api/v1"
    upload_dir: str = os.getenv("UPLOAD_DIR", "storage/uploads")
    upload_max_size_bytes: int = int(os.getenv("UPLOAD_MAX_SIZE_BYTES", str(5 * 1024 * 1024)))
    upload_max_files: int = int(os.getenv("UPLOAD_MAX_FILES", "20"))
    # SQLite keeps direct local runs lightweight; Docker overrides this with Postgres.
    database_url: str = _normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "mistralai/ministral-3b-2512")
    openrouter_api_url: str = os.getenv(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
    openrouter_referer: str = os.getenv("OPENROUTER_REFERER", "")
    openrouter_title: str = os.getenv("OPENROUTER_TITLE", os.getenv("APP_NAME", "DocAudit"))
    # Legacy aggregate timeout kept as an env fallback while the request budget is split by phase.
    openrouter_timeout_seconds: float = LEGACY_OPENROUTER_TIMEOUT_SECONDS
    openrouter_connect_timeout_seconds: float = _parse_positive_float_env(
        "OPENROUTER_CONNECT_TIMEOUT_SECONDS",
        DEFAULT_OPENROUTER_CONNECT_TIMEOUT_SECONDS,
    )
    openrouter_write_timeout_seconds: float = _parse_positive_float_env(
        "OPENROUTER_WRITE_TIMEOUT_SECONDS",
        DEFAULT_OPENROUTER_WRITE_TIMEOUT_SECONDS,
    )
    openrouter_read_timeout_seconds: float = _parse_positive_float_env(
        "OPENROUTER_READ_TIMEOUT_SECONDS",
        DEFAULT_OPENROUTER_READ_TIMEOUT_SECONDS,
    )
    openrouter_pool_timeout_seconds: float = _parse_positive_float_env(
        "OPENROUTER_POOL_TIMEOUT_SECONDS",
        DEFAULT_OPENROUTER_POOL_TIMEOUT_SECONDS,
    )
    openrouter_timeout_retries: int = int(os.getenv("OPENROUTER_TIMEOUT_RETRIES", "2"))
    openrouter_rate_limit_enabled: bool = _parse_bool_env("OPENROUTER_RATE_LIMIT_ENABLED", True)
    openrouter_rate_limit_cooldown_seconds: float = _parse_positive_float_env(
        "OPENROUTER_RATE_LIMIT_COOLDOWN_SECONDS",
        2.0,
    )
    openrouter_rate_limit_retries: int = _parse_positive_int_env(
        "OPENROUTER_RATE_LIMIT_RETRIES",
        6,
    )
    openrouter_rate_limit_retry_spread_seconds: float = _parse_positive_float_env(
        "OPENROUTER_RATE_LIMIT_RETRY_SPREAD_SECONDS",
        1.0,
    )
    celery_default_queue: str = os.getenv("CELERY_DEFAULT_QUEUE", "celery").strip() or "celery"
    celery_observed_queues: tuple[str, ...] = field(
        default_factory=lambda: _parse_unique_csv_env(
            "CELERY_OBSERVED_QUEUES",
            (os.getenv("CELERY_DEFAULT_QUEUE", "celery").strip() or "celery",),
        )
    )
    celery_inspect_timeout_seconds: float = _parse_positive_float_env(
        "CELERY_INSPECT_TIMEOUT_SECONDS",
        1.5,
    )
    celery_task_soft_time_limit_seconds: int = _default_celery_task_soft_time_limit_seconds()
    celery_task_time_limit_seconds: int = _default_celery_task_time_limit_seconds()
    observability_event_retention: int = _parse_positive_int_env(
        "OBSERVABILITY_EVENT_RETENTION",
        2000,
    )
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
