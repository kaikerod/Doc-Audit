from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from ..database import Base

json_type = JSON().with_variant(JSONB(), "postgresql")


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numero_nf: Mapped[str | None] = mapped_column(String(100))
    cnpj_emitente: Mapped[str | None] = mapped_column(String(18))
    cnpj_destinatario: Mapped[str | None] = mapped_column(String(18))
    data_emissao: Mapped[date | None] = mapped_column(Date)
    data_pagamento: Mapped[date | None] = mapped_column(Date)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    aprovador: Mapped[str | None] = mapped_column(String(255))
    descricao: Mapped[str | None] = mapped_column(Text)
    conteudo_bruto: Mapped[str | None] = mapped_column(Text)
    resposta_ia: Mapped[dict | list | None] = mapped_column(json_type)
    modelo_ia: Mapped[str | None] = mapped_column(String(100))
    tokens_consumidos: Mapped[int | None] = mapped_column(Integer)
    status_extracao: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pendente",
        server_default=text("'pendente'"),
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    upload: Mapped["Upload"] = relationship(back_populates="documentos")
    anomalias: Mapped[list["Anomalia"]] = relationship(
        back_populates="documento",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
