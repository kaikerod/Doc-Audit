from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import select

from ..config import settings
from ..database import DbSession
from ..models.anomalia import Anomalia
from ..models.aprovador_autorizado import AprovadorAutorizado
from ..models.documento import Documento
from ..models.fornecedor import Fornecedor
from ..models.upload import Upload
from .anomalia_service import DetectedAnomaly, detectar_anomalias
from .audit_service import log_audit_event
from .ia_service import extract_document_data
from ..schemas.documento import DocumentExtractionResult


class TxtDecodingError(ValueError):
    """Raised when an uploaded TXT file cannot be decoded as UTF-8."""


@dataclass(slots=True)
class ProcessedUploadBundle:
    upload: Upload
    documento: Documento
    anomalias: list[Anomalia]
    file_path: Path


@dataclass(slots=True)
class FailedUploadBundle:
    upload: Upload
    file_path: Path
    error_message: str


def decode_txt_content(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TxtDecodingError("Arquivo TXT precisa estar codificado em UTF-8.") from exc


def _load_anomaly_context(
    db: DbSession,
    *,
    exclude_document_id: UUID | None = None,
    extra_existing_invoice_keys: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    statement = select(Documento.numero_nf, Documento.cnpj_emitente)
    if exclude_document_id is not None:
        statement = statement.where(Documento.id != exclude_document_id)

    existing_invoice_keys = {
        (numero_nf, cnpj_emitente)
        for numero_nf, cnpj_emitente in db.execute(statement)
        if numero_nf and cnpj_emitente
    }
    if extra_existing_invoice_keys:
        existing_invoice_keys.update(extra_existing_invoice_keys)

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


def detect_document_anomalies(
    db: DbSession,
    extraction_payload: Mapping[str, Any],
    *,
    exclude_document_id: UUID | None = None,
    extra_existing_invoice_keys: set[tuple[str, str]] | None = None,
) -> list[DetectedAnomaly]:
    anomaly_context = _load_anomaly_context(
        db,
        exclude_document_id=exclude_document_id,
        extra_existing_invoice_keys=extra_existing_invoice_keys,
    )
    return detectar_anomalias(extraction_payload, **anomaly_context)


def populate_documento_from_extraction(
    documento: Documento,
    *,
    conteudo_bruto: str,
    extraction: DocumentExtractionResult,
    extraction_payload: dict[str, Any],
    status_extracao: str = "concluido",
) -> Documento:
    documento.numero_nf = extraction.numero_nf
    documento.cnpj_emitente = extraction.cnpj_emitente
    documento.cnpj_destinatario = extraction.cnpj_destinatario
    documento.data_emissao = extraction.data_emissao
    documento.data_pagamento = extraction.data_pagamento
    documento.valor_total = extraction.valor_total
    documento.aprovador = extraction.aprovador
    documento.descricao = extraction.descricao
    documento.conteudo_bruto = conteudo_bruto
    documento.resposta_ia = extraction_payload
    documento.modelo_ia = settings.openrouter_model
    documento.status_extracao = status_extracao
    return documento


def build_processed_upload_bundle(
    db: DbSession,
    *,
    original_name: str,
    content: bytes,
    storage_dir: Path,
    extra_existing_invoice_keys: set[tuple[str, str]] | None = None,
) -> ProcessedUploadBundle:
    storage_dir.mkdir(parents=True, exist_ok=True)

    conteudo_bruto = decode_txt_content(content)
    extraction = extract_document_data(conteudo_bruto)
    extraction_payload = extraction.model_dump(mode="json")
    detected_anomalies = detect_document_anomalies(
        db,
        extraction_payload,
        extra_existing_invoice_keys=extra_existing_invoice_keys,
    )

    upload_id = uuid4()
    documento_id = uuid4()
    stored_name = f"{uuid4()}.txt"
    file_path = storage_dir / stored_name

    upload = Upload(
        id=upload_id,
        nome_arquivo=original_name,
        caminho_arquivo=str(file_path.resolve()),
        hash_sha256=hashlib.sha256(content).hexdigest(),
        tamanho_bytes=len(content),
        status="concluido",
    )
    documento = populate_documento_from_extraction(
        Documento(id=documento_id, upload_id=upload_id),
        conteudo_bruto=conteudo_bruto,
        extraction=extraction,
        extraction_payload=extraction_payload,
    )
    anomalias = [
        Anomalia(
            documento_id=documento_id,
            codigo=anomalia.codigo,
            descricao=anomalia.descricao,
            severidade=anomalia.severidade,
        )
        for anomalia in detected_anomalies
    ]

    try:
        file_path.write_bytes(content)
    except Exception:
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return ProcessedUploadBundle(
        upload=upload,
        documento=documento,
        anomalias=anomalias,
        file_path=file_path,
    )


def build_failed_upload_bundle(
    *,
    original_name: str,
    content: bytes,
    storage_dir: Path,
    error_message: str,
) -> FailedUploadBundle:
    storage_dir.mkdir(parents=True, exist_ok=True)

    upload_id = uuid4()
    stored_name = f"{uuid4()}.txt"
    file_path = storage_dir / stored_name

    upload = Upload(
        id=upload_id,
        nome_arquivo=original_name,
        caminho_arquivo=str(file_path.resolve()),
        hash_sha256=hashlib.sha256(content).hexdigest(),
        tamanho_bytes=len(content),
        status="erro",
    )

    try:
        file_path.write_bytes(content)
    except Exception:
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return FailedUploadBundle(
        upload=upload,
        file_path=file_path,
        error_message=error_message,
    )


def persist_processed_uploads(
    db: DbSession,
    processed_uploads: list[ProcessedUploadBundle],
    *,
    usuario: str | None = None,
    ip: str | None = None,
) -> None:
    for processed_upload in processed_uploads:
        upload = processed_upload.upload
        documento = processed_upload.documento

        db.add(upload)
        db.add(documento)
        db.add_all(processed_upload.anomalias)

        log_audit_event(
            db,
            evento="processamento_iniciado",
            entidade_tipo="upload",
            entidade_id=str(upload.id),
            usuario=usuario,
            ip=ip,
            payload={
                "upload_id": str(upload.id),
                "arquivo": upload.nome_arquivo,
                "modelo": settings.openrouter_model,
            },
            commit=False,
        )
        log_audit_event(
            db,
            evento="anomalias_detectadas",
            entidade_tipo="documento",
            entidade_id=str(documento.id),
            usuario=usuario,
            ip=ip,
            payload={
                "documento_id": str(documento.id),
                "anomalias": [
                    {
                        "codigo": anomalia.codigo,
                        "descricao": anomalia.descricao,
                        "severidade": anomalia.severidade,
                    }
                    for anomalia in processed_upload.anomalias
                ],
                "quantidade": len(processed_upload.anomalias),
            },
            commit=False,
        )
        log_audit_event(
            db,
            evento="processamento_concluido",
            entidade_tipo="documento",
            entidade_id=str(documento.id),
            usuario=usuario,
            ip=ip,
            payload={
                "documento_id": str(documento.id),
                "status_extracao": documento.status_extracao,
                "upload_status": upload.status,
            },
            commit=False,
        )

    db.commit()

    for processed_upload in processed_uploads:
        db.refresh(processed_upload.upload)


def persist_failed_uploads(
    db: DbSession,
    failed_uploads: list[FailedUploadBundle],
    *,
    usuario: str | None = None,
    ip: str | None = None,
) -> None:
    for failed_upload in failed_uploads:
        upload = failed_upload.upload

        db.add(upload)
        log_audit_event(
            db,
            evento="processamento_erro",
            entidade_tipo="upload",
            entidade_id=str(upload.id),
            usuario=usuario,
            ip=ip,
            payload={
                "upload_id": str(upload.id),
                "arquivo": upload.nome_arquivo,
                "erro": failed_upload.error_message,
            },
            commit=False,
        )

    db.commit()

    for failed_upload in failed_uploads:
        db.refresh(failed_upload.upload)


def cleanup_processed_uploads(processed_uploads: list[ProcessedUploadBundle]) -> None:
    for processed_upload in processed_uploads:
        try:
            processed_upload.file_path.unlink()
        except FileNotFoundError:
            continue


def cleanup_failed_uploads(failed_uploads: list[FailedUploadBundle]) -> None:
    for failed_upload in failed_uploads:
        try:
            failed_upload.file_path.unlink()
        except FileNotFoundError:
            continue
