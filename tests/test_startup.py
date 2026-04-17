from __future__ import annotations

from unittest.mock import patch

from backend.app.database import Base, engine
from backend.app.main import initialize_database_schema


def test_initialize_database_schema_creates_all_tables() -> None:
    with patch.object(Base.metadata, "create_all") as create_all:
        initialize_database_schema()

    create_all.assert_called_once_with(bind=engine)
