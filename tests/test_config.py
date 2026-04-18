from __future__ import annotations

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

    assert config._normalize_database_url("   ") == config.DEFAULT_DATABASE_URL
