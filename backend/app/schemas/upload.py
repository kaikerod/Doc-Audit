from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UploadRead(BaseModel):
    id: UUID
    nome_arquivo: str
    caminho_arquivo: str
    hash_sha256: str
    tamanho_bytes: int
    status: str
    criado_em: datetime
    atualizado_em: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadBatchResponse(BaseModel):
    items: list[UploadRead]


class UploadListResponse(BaseModel):
    total: int
    items: list[UploadRead]
