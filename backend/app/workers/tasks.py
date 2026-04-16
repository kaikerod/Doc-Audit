from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from celery import Celery
from sqlalchemy import select

from ..config import settings
from ..database import DbSession, SessionLocal
from ..models.anomalia import Anomalia
from ..models.aprovador_autorizado import AprovadorAutorizado
from ..models.documento import Documento
from ..models.fornecedor import Fornecedor
from ..models.upload import Upload
from ..services.anomalia_service import detectar_anomalias
from ..services.audit_service import log_audit_event
from ..services.ia_service import extract_document_data

celery_app = Celery("docaudit", broker=settings.redis_url, backend=settings.redis_url)


def _load_upload_or_fail(db: DbSession, upload_id: UUID) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise ValueError(f"Upload {upload_id} nao encontrado.")
    return upload


def _get_or_create_documento(db: DbSession, upload_id: UUID, conteudo_bruto: str) -> Documento:
    documento = db.scalar(select(Documento).where(Documento.upload_id == upload_id))
    if documento is not None:
        documento.conteudo_bruto = conteudo_bruto
        return documento

    documento = Documento(
        upload_id=upload_id,
        conteudo_bruto=conteudo_bruto,
        status_extracao="processando",
    )
    db.add(documento)
    db.flush()
    return documento


def _load_anomaly_context(db: DbSession, documento: Documento) -> dict[str, Any]:
    existing_invoice_keys = {
        (numero_nf, cnpj_emitente)
        for numero_nf, cnpj_emitente in db.execute(
            select(Documento.numero_nf, Documento.cnpj_emitente).where(Documento.id != documento.id)
        )
        if numero_nf and cnpj_emitente
    }
    fornecedores_cnpj_values = {
        cnpj for cnpj, in db.execute(select(Fornecedor.cnpj).where(Fornecedor.ativo.is_(True)))
    }
    aprovadores_autorizados_values = {
        nome for nome, in db.execute(select(AprovadorAutorizado.nome).where(AprovadorAutorizado.ativo.is_(True)))
    }
    return {
        "existing_invoice_keys": existing_invoice_keys,
        "fornecedores_cnpj": fornecedores_cnpj_values or None,
        "aprovadores_autorizados": aprovadores_autorizados_values or None,
    }


def _replace_document_anomalies(db: DbSession, documento: Documento, anomalies: list[Any]) -> None:
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
        documento = _get_or_create_documento(db, upload.id, conteudo_bruto)
        db.commit()
        db.refresh(documento)

        extraction = extract_document_data(conteudo_bruto)
        extraction_payload = extraction.model_dump(mode="json")

        documento.numero_nf = extraction.numero_nf
        documento.cnpj_emitente = extraction.cnpj_emitente
        documento.cnpj_destinatario = extraction.cnpj_destinatario
        documento.data_emissao = extraction.data_emissao
        documento.data_pagamento = extraction.data_pagamento
        documento.valor_total = extraction.valor_total
        documento.aprovador = extraction.aprovador
        documento.descricao = extraction.descricao
        documento.resposta_ia = extraction_payload
        documento.modelo_ia = settings.openrouter_model

        anomaly_context = _load_anomaly_context(db, documento)
        anomalies = detectar_anomalias(extraction_payload, **anomaly_context)
        _replace_document_anomalies(db, documento, anomalies)

        documento.status_extracao = "concluído"
        upload.status = "concluído"
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
    except Exception as exc:
        db.rollback()

        upload = _load_upload_or_fail(db, resolved_upload_id)
        upload.status = "erro"
        if documento is not None:
            documento = db.get(Documento, documento.id)
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
                "erro": str(exc),
            },
        )
        raise


@celery_app.task(name="backend.app.workers.tasks.process_upload_document")
def process_upload_document(upload_id: str) -> str:
    db = SessionLocal()
    try:
        documento = process_upload_document_pipeline(upload_id, db)
        return str(documento.id)
    finally:
        db.close()
