from __future__ import annotations

from backend.app import database


def test_engine_kwargs_disable_psycopg_prepared_statements(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        database.settings,
        "database_url",
        "postgresql+psycopg://docaudit:docaudit@db:5432/docaudit",
    )

    assert database._engine_kwargs() == {
        "pool_pre_ping": True,
        "connect_args": {"prepare_threshold": None},
    }


def test_engine_kwargs_configure_sqlite_thread_safety(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        database.settings,
        "database_url",
        "sqlite+pysqlite:///:memory:",
    )

    assert database._engine_kwargs() == {
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
    }
