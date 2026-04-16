from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func, false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from ..database import Base

anomalia_severidade_enum = Enum(
    "CRITICA",
    "ALTA",
    "MEDIA",
    name="anomalia_severidade",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


class Anomalia(Base):
    __tablename__ = "anomalias"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    documento_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documentos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    severidade: Mapped[str] = mapped_column(anomalia_severidade_enum, nullable=False)
    resolvida: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=false())
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    documento: Mapped["Documento"] = relationship(back_populates="anomalias")
