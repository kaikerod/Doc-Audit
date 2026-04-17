from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import DbSession, get_db
from ..models.documento import Documento
from ..models.upload import Upload
from ..schemas.documento import DocumentoAnomaliaRead, DocumentoListItem, DocumentoListResponse

router = APIRouter(prefix=f"{settings.api_v1_prefix}/documentos", tags=["documentos"])


def _normalize_status(status: Any, default: str = "pendente") -> str:
    if not isinstance(status, str):
        return default

    normalized = status.strip()
    return normalized or default


def _normalize_filename(filename: Any) -> str:
    if not isinstance(filename, str):
        return "arquivo_sem_nome.txt"

    normalized = filename.strip()
    return normalized or "arquivo_sem_nome.txt"


def _datetime_sort_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return ""


def _build_summary(status: Any, flags: list[DocumentoAnomaliaRead]) -> str:
    normalized_status = _normalize_status(status).casefold()
    if normalized_status == "erro":
        return "Processamento interrompido com erro."
    if normalized_status in {"pendente", "processando"}:
        return "Upload recebido e aguardando pipeline de processamento."
    if flags:
        return f"{len(flags)} anomalia(s) detectada(s) para revisao."
    return "Processamento concluido sem anomalias."


def _select_latest_document(upload: Upload) -> Documento | None:
    if not upload.documentos:
        return None
    return max(upload.documentos, key=lambda documento: _datetime_sort_key(documento.criado_em))


def _map_document_flags(documento: Documento) -> list[DocumentoAnomaliaRead]:
    flags: list[DocumentoAnomaliaRead] = []
    ordered_anomalies = sorted(
        documento.anomalias,
        key=lambda item: _datetime_sort_key(item.criado_em),
    )

    for anomalia in ordered_anomalies:
        try:
            flags.append(DocumentoAnomaliaRead.model_validate(anomalia))
        except ValidationError:
            continue

    return flags


def _map_upload_to_list_item(upload: Upload) -> DocumentoListItem:
    documento = _select_latest_document(upload)

    if documento is None:
        status = _normalize_status(upload.status)
        flags: list[DocumentoAnomaliaRead] = []
        return DocumentoListItem(
            id=str(upload.id),
            upload_id=str(upload.id),
            documento_id=None,
            nome_arquivo=_normalize_filename(upload.nome_arquivo),
            status=status,
            resumo=_build_summary(status, flags),
            flags=flags,
        )

    flags = _map_document_flags(documento)
    status = _normalize_status(documento.status_extracao)

    return DocumentoListItem(
        id=str(documento.id),
        upload_id=str(upload.id),
        documento_id=str(documento.id),
        nome_arquivo=_normalize_filename(upload.nome_arquivo),
        numero_nf=documento.numero_nf,
        cnpj_emitente=documento.cnpj_emitente,
        data_emissao=documento.data_emissao,
        data_pagamento=documento.data_pagamento,
        valor_total=documento.valor_total,
        aprovador=documento.aprovador,
        descricao=documento.descricao,
        status=status,
        resumo=_build_summary(status, flags),
        flags=flags,
    )


@router.get(
    "",
    response_model=DocumentoListResponse,
    summary="Lista todos os documentos processados",
    description="Retorna uma lista paginada de todos os uploads realizados, incluindo os dados extraídos pela IA e as flags de anomalia detectadas.",
)
def list_documentos(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: DbSession = Depends(get_db),
) -> DocumentoListResponse:
    total = db.scalar(select(func.count()).select_from(Upload)) or 0
    uploads = db.scalars(
        select(Upload)
        .options(selectinload(Upload.documentos).selectinload(Documento.anomalias))
        .order_by(Upload.criado_em.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return DocumentoListResponse(
        total=total,
        items=[_map_upload_to_list_item(upload) for upload in uploads],
    )
