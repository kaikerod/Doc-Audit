from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Base declarativa para todos os modelos ORM."""


def _uses_psycopg_postgres(database_url: str) -> bool:
    return database_url.startswith("postgresql+psycopg")


def _engine_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }
    connect_args: dict[str, object] = {}

    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif _uses_psycopg_postgres(settings.database_url):
        # Serverless/database-pooler setups may reuse a client connection across
        # different backend sessions, which breaks psycopg prepared statements.
        connect_args["prepare_threshold"] = None

    if connect_args:
        kwargs["connect_args"] = connect_args

    return kwargs


engine: Engine = create_engine(
    settings.database_url,
    **_engine_kwargs(),
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)

DbSession = Session


def get_db() -> Generator[DbSession, None, None]:
    """Dependency helper para rotas FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
