from __future__ import annotations

from pathlib import Path
from uuid import UUID

from celery import Celery
from sqlalchemy import select

from ..config import settings
from ..database import DbSession, SessionLocal
from ..models.anomalia import Anomalia
from ..models.documento import Documento
from ..models.upload import Upload
from ..services.anomalia_service import DetectedAnomaly
from ..services.audit_service import log_audit_event
from ..services.document_processing_service import (
    detect_document_anomalies,
    populate_documento_from_extraction,
)
from ..services.ia_service import extract_document_data

celery_app = Celery("docaudit", broker=settings.redis_url, backend=settings.redis_url)


def _load_upload_or_fail(db: DbSession, upload_id: UUID) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise ValueError(f"Upload {upload_id} nao encontrado.")
    return upload


def _load_existing_documento(db: DbSession, upload_id: UUID) -> Documento | None:
    return db.scalar(select(Documento).where(Documento.upload_id == upload_id))


def _replace_document_anomalies(
    db: DbSession, documento: Documento, anomalies: list[DetectedAnomaly]
) -> None:
    documento.anomalias.clear()
    db.flush()

    for anomaly in anomalies:
        db.add(
            Anomalia(
                documento_id=documento.id,
                codigo=anomaly.codigo,
                descricao=anomaly.descricao,
                severidade=anomaly.severidade,
            )
        )


def process_upload_document_pipeline(upload_id: str | UUID, db: DbSession) -> Documento:
    resolved_upload_id = UUID(str(upload_id))
    upload = _load_upload_or_fail(db, resolved_upload_id)
    upload.status = "processando"
    db.commit()
    db.refresh(upload)

    log_audit_event(
        db,
        evento="processamento_iniciado",
        entidade_tipo="upload",
        entidade_id=str(upload.id),
        payload={
            "upload_id": str(upload.id),
            "arquivo": upload.nome_arquivo,
            "modelo": settings.openrouter_model,
        },
    )

    documento: Documento | None = None

    try:
        conteudo_bruto = Path(upload.caminho_arquivo).read_text(encoding="utf-8")
        documento = _load_existing_documento(db, upload.id)

        extraction = extract_document_data(conteudo_bruto)
        extraction_payload = extraction.model_dump(mode="json")
        anomalies = detect_document_anomalies(
            db,
            extraction_payload,
            exclude_document_id=documento.id if documento is not None else None,
        )

        if documento is None:
            documento = Documento(upload_id=upload.id)
            db.add(documento)
            db.flush()

        populate_documento_from_extraction(
            documento,
            conteudo_bruto=conteudo_bruto,
            extraction=extraction,
            extraction_payload=extraction_payload,
        )
        _replace_document_anomalies(db, documento, anomalies)

        upload.status = "concluido"
        db.commit()
        db.refresh(documento)

        log_audit_event(
            db,
            evento="anomalias_detectadas",
            entidade_tipo="documento",
            entidade_id=str(documento.id),
            payload={
                "documento_id": str(documento.id),
                "anomalias": [
                    {
                        "codigo": anomaly.codigo,
                        "descricao": anomaly.descricao,
                        "severidade": anomaly.severidade,
                    }
                    for anomaly in anomalies
                ],
                "quantidade": len(anomalies),
            },
        )
        log_audit_event(
            db,
            evento="processamento_concluido",
            entidade_tipo="documento",
            entidade_id=str(documento.id),
            payload={
                "documento_id": str(documento.id),
                "status_extracao": documento.status_extracao,
                "upload_status": upload.status,
            },
        )
        return documento
    except Exception:
        db.rollback()
        raise


def mark_upload_processing_error(upload_id: str | UUID, db: DbSession, *, error_message: str) -> None:
    resolved_upload_id = UUID(str(upload_id))
    upload = _load_upload_or_fail(db, resolved_upload_id)
    upload.status = "erro"

    documento = _load_existing_documento(db, upload.id)
    if documento is not None:
        documento.status_extracao = "erro"

    db.commit()

    log_audit_event(
        db,
        evento="processamento_erro",
        entidade_tipo="upload",
        entidade_id=str(upload.id),
        payload={
            "upload_id": str(upload.id),
            "erro": error_message,
        },
    )


@celery_app.task(name="backend.app.workers.tasks.process_upload_document")
def process_upload_document(upload_id: str) -> str:
    db = SessionLocal()
    try:
        documento = process_upload_document_pipeline(upload_id, db)
        return str(documento.id)
    except Exception as exc:
        db.rollback()
        mark_upload_processing_error(upload_id, db, error_message=str(exc))
        raise
    finally:
        db.close()
