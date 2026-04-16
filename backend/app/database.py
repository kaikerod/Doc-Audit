from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Base declarativa para todos os modelos ORM."""


def _engine_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }

    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

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
