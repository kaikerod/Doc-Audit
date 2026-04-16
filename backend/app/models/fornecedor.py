from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Fornecedor(Base):
    __tablename__ = "fornecedores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False, unique=True)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=true())
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
