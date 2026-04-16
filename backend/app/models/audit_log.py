from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid
from uuid import UUID, uuid4

from ..database import Base

json_type = JSON().with_variant(JSONB(), "postgresql")
ip_type = String(45).with_variant(INET(), "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    evento: Mapped[str] = mapped_column(String(100), nullable=False)
    entidade_tipo: Mapped[str | None] = mapped_column(String(100))
    entidade_id: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(ip_type)
    payload: Mapped[dict | list | None] = mapped_column(json_type)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
