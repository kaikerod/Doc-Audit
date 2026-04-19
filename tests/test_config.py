from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app import config


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        (
            "postgresql+psycopg://docaudit:docaudit@db:5432/docaudit",
            "postgresql+psycopg://docaudit:docaudit@127.0.0.1:5432/docaudit",
        ),
        (
            "postgresql://docaudit:docaudit@db:5432/docaudit",
            "postgresql+psycopg://docaudit:docaudit@127.0.0.1:5432/docaudit",
        ),
        (
            "sqlite+pysqlite:///./docaudit.db",
            "sqlite+pysqlite:///./docaudit.db",
        ),
    ],
)
def test_normalize_database_url_for_host_runs(
    monkeypatch: pytest.MonkeyPatch, database_url: str, expected: str
) -> None:
    monkeypatch.setattr(config, "_is_running_in_container", lambda: False)

    assert config._normalize_database_url(database_url) == expected


def test_normalize_database_url_keeps_docker_host_inside_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://docaudit:docaudit@db:5432/docaudit"
    monkeypatch.setattr(config, "_is_running_in_container", lambda: True)

    assert config._normalize_database_url(database_url) == database_url


def test_normalize_database_url_uses_sqlite_default_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "_is_running_in_container", lambda: False)

    assert config._normalize_database_url("   ") == config.TEST_DATABASE_URL


def test_resolve_database_url_prefers_database_url_over_vercel_postgres_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://primary")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://fallback")

    assert config._resolve_database_url() == "postgresql+psycopg://primary"


def test_resolve_database_url_uses_vercel_postgres_url_when_database_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgresql://docaudit:docaudit@db:5432/docaudit")
    monkeypatch.setattr(config, "_is_running_in_container", lambda: False)

    assert (
        config._resolve_database_url()
        == "postgresql+psycopg://docaudit:docaudit@127.0.0.1:5432/docaudit"
    )


def test_resolve_database_url_prefers_non_pooling_postgres_url_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_URL_NON_POOLING", "postgresql://non-pooling")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://pooled")
    monkeypatch.setattr(config, "_is_running_in_container", lambda: False)

    assert config._resolve_database_url() == "postgresql+psycopg://non-pooling"


def test_normalize_database_url_strips_supabase_query_params_for_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "_is_running_in_container", lambda: False)

    normalized_url = config._normalize_database_url(
        "postgres://user:pass@aws-1-sa-east-1.pooler.supabase.com:6543/postgres"
        "?sslmode=require&supa=base-pooler.x"
    )
    parsed_url = config.make_url(normalized_url)

    assert parsed_url.drivername == "postgresql+psycopg"
    assert parsed_url.query == {"sslmode": "require"}


def test_resolve_database_url_uses_local_postgres_default_outside_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL_NON_POOLING", raising=False)
    monkeypatch.delenv("POSTGRES_PRISMA_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)
    monkeypatch.setattr(config, "_is_test_environment", lambda: False)
    monkeypatch.setattr(config, "_is_running_in_container", lambda: False)

    assert (
        config._resolve_database_url()
        == "postgresql+psycopg://docaudit:docaudit@127.0.0.1:5432/docaudit"
    )


def test_strip_env_value_removes_wrapping_quotes() -> None:
    assert config._strip_env_value('"valor"') == "valor"
    assert config._strip_env_value("'valor'") == "valor"
    assert config._strip_env_value("valor") == "valor"


def _write_test_dotenv(contents: str) -> Path:
    dotenv_path = Path.cwd() / "tests" / ".tmp" / f"{uuid4()}.env"
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.write_text(contents, encoding="utf-8")
    return dotenv_path


def test_load_dotenv_file_populates_missing_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv_path = _write_test_dotenv(
        "OPENROUTER_API_KEY=test-key\nOPENROUTER_MODEL='model/test'\nIGNORED_LINE\n"
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    try:
        config._load_dotenv_file(dotenv_path)
    finally:
        dotenv_path.unlink(missing_ok=True)

    assert config.os.environ["OPENROUTER_API_KEY"] == "test-key"
    assert config.os.environ["OPENROUTER_MODEL"] == "model/test"


def test_load_dotenv_file_does_not_override_existing_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = _write_test_dotenv("OPENROUTER_API_KEY=dotenv-key\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "existing-key")

    try:
        config._load_dotenv_file(dotenv_path)
    finally:
        dotenv_path.unlink(missing_ok=True)

    assert config.os.environ["OPENROUTER_API_KEY"] == "existing-key"


def test_load_dotenv_file_is_skipped_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = _write_test_dotenv("OPENROUTER_API_KEY=dotenv-key\n")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("VERCEL", "1")

    try:
        config._load_dotenv_file(dotenv_path)
    finally:
        dotenv_path.unlink(missing_ok=True)

    assert config.os.environ.get("OPENROUTER_API_KEY") is None


def test_resolve_processing_mode_defaults_to_sync_outside_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DOC_AUDIT_PROCESSING_MODE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)

    assert config._resolve_processing_mode() == "sync"


def test_resolve_processing_mode_defaults_to_sync_on_vercel_when_redis_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DOC_AUDIT_PROCESSING_MODE", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("REDIS_URL", "rediss://default:test@redis.example.com:6379")

    assert config._resolve_processing_mode() == "sync"


def test_resolve_processing_mode_defaults_to_sync_on_vercel_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DOC_AUDIT_PROCESSING_MODE", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert config._resolve_processing_mode() == "sync"


def test_default_upload_dir_uses_temp_directory_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERCEL", "1")

    assert Path(config._default_upload_dir()).parts[-2:] == ("docaudit", "uploads")


def test_default_database_url_uses_sqlite_during_tests() -> None:
    assert config._default_database_url() == config.TEST_DATABASE_URL


def test_default_database_url_uses_local_postgres_outside_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "_is_test_environment", lambda: False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)

    assert config._default_database_url() == config.LOCAL_POSTGRES_DATABASE_URL


def test_default_database_url_is_empty_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERCEL", "1")

    assert config._default_database_url() == ""


def test_resolve_database_url_requires_persistent_database_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL_NON_POOLING", raising=False)
    monkeypatch.delenv("POSTGRES_PRISMA_URL", raising=False)
    monkeypatch.setenv("VERCEL", "1")

    with pytest.raises(
        RuntimeError,
        match="Vercel exige um banco persistente",
    ):
        config._resolve_database_url()
