from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CHAR, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from ..database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
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
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
