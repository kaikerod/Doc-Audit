from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import DbSession
from ..models.documento import Documento
from ..models.upload import Upload
from .audit_service import log_audit_event


class UploadNotFoundError(LookupError):
    """Raised when an upload does not exist."""


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _build_document_payload(documento: Documento) -> dict[str, str | None]:
    return {
        "documento_id": str(documento.id),
        "numero_nf": documento.numero_nf,
        "cnpj_emitente": documento.cnpj_emitente,
        "data_emissao": documento.data_emissao.isoformat() if documento.data_emissao else None,
        "data_pagamento": documento.data_pagamento.isoformat() if documento.data_pagamento else None,
        "valor_total": _serialize_decimal(documento.valor_total),
        "status_extracao": documento.status_extracao,
    }


def delete_upload(
    db: DbSession,
    upload_id: UUID,
    *,
    usuario: str | None = None,
    ip: str | None = None,
) -> None:
    upload = db.scalar(
        select(Upload)
        .options(selectinload(Upload.documentos))
        .where(Upload.id == upload_id)
    )
    if upload is None:
        raise UploadNotFoundError(f"Upload {upload_id} nao encontrado.")

    file_path = Path(upload.caminho_arquivo)
    ordered_documents = sorted(
        upload.documentos,
        key=lambda item: item.criado_em.isoformat() if item.criado_em else "",
    )
    payload = {
        "upload_id": str(upload.id),
        "nome_arquivo": upload.nome_arquivo,
        "status_upload": upload.status,
        "documentos": [_build_document_payload(documento) for documento in ordered_documents],
    }

    log_audit_event(
        db,
        evento="EXCLUSAO_UPLOAD",
        entidade_tipo="upload",
        entidade_id=str(upload.id),
        usuario=usuario,
        ip=ip,
        payload=payload,
        commit=False,
    )
    db.flush()
    db.delete(upload)
    db.commit()

    try:
        file_path.unlink()
    except FileNotFoundError:
        return


def delete_all_uploads(
    db: DbSession,
    *,
    usuario: str | None = None,
    ip: str | None = None,
) -> int:
    """Delete every upload and its associated documents. Returns the count of deleted uploads."""
    uploads = db.scalars(
        select(Upload).options(selectinload(Upload.documentos))
    ).all()

    if not uploads:
        return 0

    file_paths: list[Path] = []
    deleted_count = 0

    for upload in uploads:
        file_paths.append(Path(upload.caminho_arquivo))
        db.delete(upload)
        deleted_count += 1

    log_audit_event(
        db,
        evento="EXCLUSAO_TOTAL_UPLOADS",
        entidade_tipo="upload",
        entidade_id="*",
        usuario=usuario,
        ip=ip,
        payload={"total_excluido": deleted_count},
        commit=False,
    )
    db.flush()
    db.commit()

    for file_path in file_paths:
        try:
            file_path.unlink()
        except FileNotFoundError:
            continue

    return deleted_count
