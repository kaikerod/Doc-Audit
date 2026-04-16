from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import DbSession, get_db
from ..models.documento import Documento
from ..models.upload import Upload
from ..schemas.documento import DocumentoAnomaliaRead, DocumentoListItem, DocumentoListResponse

router = APIRouter(prefix=f"{settings.api_v1_prefix}/documentos", tags=["documentos"])


def _build_summary(status: str, flags: list[DocumentoAnomaliaRead]) -> str:
    normalized_status = status.casefold()
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
    return max(upload.documentos, key=lambda documento: documento.criado_em or datetime.min)


def _map_upload_to_list_item(upload: Upload) -> DocumentoListItem:
    documento = _select_latest_document(upload)

    if documento is None:
        status = upload.status
        flags: list[DocumentoAnomaliaRead] = []
        return DocumentoListItem(
            id=str(upload.id),
            upload_id=str(upload.id),
            documento_id=None,
            nome_arquivo=upload.nome_arquivo,
            status=status,
            resumo=_build_summary(status, flags),
            flags=flags,
        )

    flags = [
        DocumentoAnomaliaRead.model_validate(anomalia)
        for anomalia in sorted(documento.anomalias, key=lambda item: item.criado_em or datetime.min)
    ]

    return DocumentoListItem(
        id=str(documento.id),
        upload_id=str(upload.id),
        documento_id=str(documento.id),
        nome_arquivo=upload.nome_arquivo,
        numero_nf=documento.numero_nf,
        cnpj_emitente=documento.cnpj_emitente,
        data_emissao=documento.data_emissao,
        data_pagamento=documento.data_pagamento,
        valor_total=documento.valor_total,
        aprovador=documento.aprovador,
        descricao=documento.descricao,
        status=documento.status_extracao,
        resumo=_build_summary(documento.status_extracao, flags),
        flags=flags,
    )


@router.get("", response_model=DocumentoListResponse)
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
