from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.config import settings
from backend.app.database import Base, engine
from backend.app.main import initialize_database_schema


def test_initialize_database_schema_creates_all_tables() -> None:
    with patch.object(Base.metadata, "create_all") as create_all, patch.object(
        settings,
        "auto_create_schema",
        True,
    ):
        initialize_database_schema()

    create_all.assert_called_once_with(bind=engine)


def test_initialize_database_schema_skips_when_auto_create_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auto_create_schema", False)

    with patch.object(Base.metadata, "create_all") as create_all:
        initialize_database_schema()

    create_all.assert_not_called()
