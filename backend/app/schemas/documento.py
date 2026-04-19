from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DOCUMENT_EXTRACTION_FIELDS = (
    "numero_nf",
    "cnpj_emitente",
    "cnpj_destinatario",
    "data_emissao",
    "data_pagamento",
    "valor_total",
    "aprovador",
    "descricao",
)


class DocumentExtractionResult(BaseModel):
    numero_nf: str | None = None
    cnpj_emitente: str | None = None
    cnpj_destinatario: str | None = None
    data_emissao: date | None = None
    data_pagamento: date | None = None
    valor_total: Decimal | None = None
    aprovador: str | None = None
    descricao: str | None = None
    confiancas: dict[str, float | None] = Field(default_factory=dict)
    extraction_failed_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("confiancas")
    @classmethod
    def validate_confidences(cls, value: dict[str, float | None]) -> dict[str, float | None]:
        normalized: dict[str, float | None] = {}
        for field_name in DOCUMENT_EXTRACTION_FIELDS:
            confidence = value.get(field_name)
            if confidence is None:
                normalized[field_name] = None
                continue
            if not 0 <= confidence <= 1:
                raise ValueError(f"Confianca invalida para {field_name}: {confidence}")
            normalized[field_name] = confidence
        return normalized

    @field_validator("extraction_failed_fields")
    @classmethod
    def validate_failed_fields(cls, value: list[str]) -> list[str]:
        invalid_fields = [field_name for field_name in value if field_name not in DOCUMENT_EXTRACTION_FIELDS]
        if invalid_fields:
            raise ValueError(f"Campos invalidos em extraction_failed_fields: {invalid_fields}")
        return list(dict.fromkeys(value))

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        data.setdefault("confiancas", {})
        data.setdefault("extraction_failed_fields", [])
        return data


class DocumentoAnomaliaRead(BaseModel):
    codigo: str
    descricao: str
    severidade: str

    model_config = ConfigDict(from_attributes=True)


class DocumentoListItem(BaseModel):
    id: str
    upload_id: str
    documento_id: str | None = None
    nome_arquivo: str
    numero_nf: str | None = None
    cnpj_emitente: str | None = None
    data_emissao: date | None = None
    data_pagamento: date | None = None
    valor_total: Decimal | None = None
    aprovador: str | None = None
    descricao: str | None = None
    status: str
    resumo: str
    flags: list[DocumentoAnomaliaRead] = Field(default_factory=list)


class DocumentoListStats(BaseModel):
    total: int
    with_flags: int
    critical: int
    processing: int


class DocumentoListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool
    stats: DocumentoListStats | None = None
    items: list[DocumentoListItem]
