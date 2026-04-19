from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from ..config import settings
from ..database import DbSession, SessionLocal
from ..models.anomalia import Anomalia
from ..models.documento import Documento
from ..models.upload import Upload
from ..observability import elapsed_ms, log_observability_event, timestamp_diff_ms, utcnow_iso
from ..services.anomalia_service import DetectedAnomaly
from ..services.audit_service import log_audit_event
from ..services.document_processing_service import (
    decode_txt_content,
    detect_document_anomalies,
    populate_documento_from_extraction,
)
from ..services.ia_service import (
    OpenRouterTimeoutError,
    OpenRouterUpstreamError,
    extract_document_data,
)
from ..services.upload_queue_payload_service import (
    delete_staged_upload_content,
    get_staged_upload_content,
)

celery_app = Celery("docaudit", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
)
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class UploadProcessingSnapshot:
    upload_id: UUID
    file_path: Path


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


def _mark_upload_processing_started(db: DbSession, upload: Upload) -> None:
    if upload.status == "processando":
        return

    upload.status = "processando"
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
        commit=False,
    )
    db.commit()
    db.refresh(upload)


def _prepare_upload_processing(db: DbSession, upload_id: UUID) -> UploadProcessingSnapshot:
    upload = _load_upload_or_fail(db, upload_id)
    _mark_upload_processing_started(db, upload)
    return UploadProcessingSnapshot(
        upload_id=upload.id,
        file_path=Path(upload.caminho_arquivo),
    )


def _read_upload_content(processing_snapshot: UploadProcessingSnapshot) -> str:
    try:
        return processing_snapshot.file_path.read_text(encoding="utf-8")
    except OSError as exc:
        staged_content = get_staged_upload_content(processing_snapshot.upload_id)
        if staged_content is None:
            raise RuntimeError(
                "Conteudo do upload nao esta disponivel no filesystem local do worker "
                "nem no staging temporario do Redis."
            ) from exc

        return decode_txt_content(staged_content)


def _persist_processed_document(
    db: DbSession,
    *,
    upload_id: UUID,
    conteudo_bruto: str,
    extraction: Any,
) -> Documento:
    upload = _load_upload_or_fail(db, upload_id)
    documento = _load_existing_documento(db, upload.id)
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
        commit=False,
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
        commit=False,
    )
    db.commit()
    db.refresh(documento)
    return documento


def _should_retry_upload_processing(exc: Exception, retry_count: int) -> bool:
    if retry_count >= _resolve_task_max_retries(exc):
        return False

    if isinstance(exc, OpenRouterTimeoutError):
        return True

    return isinstance(exc, OpenRouterUpstreamError) and exc.retryable


def _resolve_task_max_retries(exc: Exception) -> int:
    if isinstance(exc, OpenRouterUpstreamError) and exc.status_code == 429:
        return settings.openrouter_rate_limit_retries

    return settings.openrouter_timeout_retries


def _resolve_rate_limit_retry_spread_seconds(task_id: str | None, task_attempt: int) -> float:
    max_spread_seconds = settings.openrouter_rate_limit_retry_spread_seconds
    if not max_spread_seconds:
        return 0.0

    if task_id:
        digest = sha256(task_id.encode("utf-8")).digest()[0] / 255
        return round(digest * max_spread_seconds, 3)

    return round(min(float(task_attempt - 1) * 0.25, max_spread_seconds), 3)


def _resolve_task_retry_delay_seconds(
    exc: Exception,
    task_attempt: int,
    *,
    task_id: str | None,
) -> float:
    if isinstance(exc, OpenRouterTimeoutError) and exc.retry_delay_seconds is not None:
        return exc.retry_delay_seconds

    if (
        isinstance(exc, OpenRouterUpstreamError)
        and exc.status_code == 429
        and exc.retry_after_seconds is not None
    ):
        return round(
            exc.retry_after_seconds + _resolve_rate_limit_retry_spread_seconds(task_id, task_attempt),
            3,
        )

    if isinstance(exc, OpenRouterUpstreamError) and exc.retry_after_seconds is not None:
        return exc.retry_after_seconds

    return min(float(task_attempt), 3.0)


def _finalize_retryable_processing_error(exc: Exception) -> Exception:
    if isinstance(exc, OpenRouterTimeoutError):
        total_attempts = settings.openrouter_timeout_retries + 1
        return OpenRouterTimeoutError(
            f"Timeout ao chamar OpenRouter apos {total_attempts} tentativas.",
            timeout_phase=exc.timeout_phase,
            phase_timeout_seconds=exc.phase_timeout_seconds,
            timeout_budget_seconds=exc.timeout_budget_seconds,
        )

    return exc


def process_upload_document_pipeline(
    upload_id: str | UUID,
    *,
    request_context: dict[str, Any] | None = None,
) -> Documento:
    resolved_upload_id = UUID(str(upload_id))
    db = SessionLocal()
    try:
        processing_snapshot = _prepare_upload_processing(db, resolved_upload_id)
    finally:
        db.close()

    conteudo_bruto = _read_upload_content(processing_snapshot)
    extraction = extract_document_data(conteudo_bruto, request_context=request_context)

    db = SessionLocal()
    try:
        return _persist_processed_document(
            db,
            upload_id=processing_snapshot.upload_id,
            conteudo_bruto=conteudo_bruto,
            extraction=extraction,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def mark_upload_processing_error(upload_id: str | UUID, db: DbSession, *, error_message: str) -> None:
    resolved_upload_id = UUID(str(upload_id))
    upload = _load_upload_or_fail(db, resolved_upload_id)
    upload.status = "erro"

    documento = _load_existing_documento(db, upload.id)
    if documento is not None:
        documento.status_extracao = "erro"

    log_audit_event(
        db,
        evento="processamento_erro",
        entidade_tipo="upload",
        entidade_id=str(upload.id),
        payload={
            "upload_id": str(upload.id),
            "erro": error_message,
        },
        commit=False,
    )
    db.commit()


def _mark_upload_processing_error_with_new_session(
    upload_id: str | UUID,
    *,
    error_message: str,
) -> None:
    db = SessionLocal()
    try:
        mark_upload_processing_error(upload_id, db, error_message=error_message)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(
    name="backend.app.workers.tasks.process_upload_document",
    bind=True,
    soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    time_limit=settings.celery_task_time_limit_seconds,
)
def process_upload_document(
    self,
    upload_id: str,
    queued_at: str | None = None,
    countdown_seconds: int | float | None = None,
) -> str:
    task_id = getattr(self.request, "id", None)
    retry_count = int(getattr(self.request, "retries", 0) or 0)
    task_attempt = retry_count + 1
    started_at = utcnow_iso()
    task_started = perf_counter()
    request_context = {
        "upload_id": upload_id,
        "task_id": task_id,
        "task_attempt": task_attempt,
        "task_retry_count": retry_count,
        "max_task_attempts": max(
            settings.openrouter_timeout_retries,
            settings.openrouter_rate_limit_retries,
        )
        + 1,
        "max_timeout_attempts": settings.openrouter_timeout_retries + 1,
        "max_rate_limit_attempts": settings.openrouter_rate_limit_retries + 1,
        "task_soft_time_limit_seconds": settings.celery_task_soft_time_limit_seconds,
        "task_time_limit_seconds": settings.celery_task_time_limit_seconds,
    }

    log_observability_event(
        logger,
        "upload_processing_started",
        upload_id=upload_id,
        task_id=task_id,
        queued_at=queued_at,
        started_at=started_at,
        queue_wait_ms=timestamp_diff_ms(queued_at, started_at),
        countdown_seconds=countdown_seconds,
        task_attempt=task_attempt,
        retry_count=retry_count,
        soft_time_limit_seconds=settings.celery_task_soft_time_limit_seconds,
        time_limit_seconds=settings.celery_task_time_limit_seconds,
    )

    try:
        documento = process_upload_document_pipeline(
            upload_id,
            request_context=request_context,
        )
        completed_at = utcnow_iso()
        log_observability_event(
            logger,
            "upload_processing_completed",
            upload_id=upload_id,
            task_id=task_id,
            documento_id=str(documento.id),
            started_at=started_at,
            completed_at=completed_at,
            total_latency_ms=elapsed_ms(task_started),
            task_attempt=task_attempt,
            retry_count=retry_count,
            soft_time_limit_seconds=settings.celery_task_soft_time_limit_seconds,
            time_limit_seconds=settings.celery_task_time_limit_seconds,
        )
        delete_staged_upload_content(upload_id)
        return str(documento.id)
    except (OpenRouterTimeoutError, OpenRouterUpstreamError) as exc:
        if _should_retry_upload_processing(exc, retry_count):
            retry_delay_seconds = _resolve_task_retry_delay_seconds(
                exc,
                task_attempt,
                task_id=task_id,
            )
            retry_queued_at = utcnow_iso()
            log_observability_event(
                logger,
                "upload_processing_retry_scheduled",
                level=logging.WARNING,
                upload_id=upload_id,
                task_id=task_id,
                started_at=started_at,
                retry_queued_at=retry_queued_at,
                retry_delay_seconds=retry_delay_seconds,
                total_latency_ms=elapsed_ms(task_started),
                task_attempt=task_attempt,
                retry_count=retry_count,
                soft_time_limit_seconds=settings.celery_task_soft_time_limit_seconds,
                time_limit_seconds=settings.celery_task_time_limit_seconds,
                exception_class=exc.__class__.__name__,
                error_message=str(exc),
                status_code=getattr(exc, "status_code", None),
                rate_limit_scope=getattr(exc, "rate_limit_scope", None),
                rate_limit_source=getattr(exc, "rate_limit_source", None),
                timeout_phase=getattr(exc, "timeout_phase", None),
                phase_timeout_seconds=getattr(exc, "phase_timeout_seconds", None),
                timeout_budget_seconds=getattr(exc, "timeout_budget_seconds", None),
            )
            raise self.retry(
                exc=exc,
                countdown=retry_delay_seconds,
                args=(upload_id,),
                kwargs={
                    "queued_at": retry_queued_at,
                    "countdown_seconds": retry_delay_seconds,
                },
                max_retries=_resolve_task_max_retries(exc),
            )

        final_exc = _finalize_retryable_processing_error(exc)
        failed_at = utcnow_iso()
        log_observability_event(
            logger,
            "upload_processing_failed",
            level=logging.ERROR,
            upload_id=upload_id,
            task_id=task_id,
            started_at=started_at,
            failed_at=failed_at,
            total_latency_ms=elapsed_ms(task_started),
            task_attempt=task_attempt,
            retry_count=retry_count,
            soft_time_limit_seconds=settings.celery_task_soft_time_limit_seconds,
            time_limit_seconds=settings.celery_task_time_limit_seconds,
            exception_class=final_exc.__class__.__name__,
            error_message=str(final_exc),
            status_code=getattr(final_exc, "status_code", None),
            rate_limit_scope=getattr(final_exc, "rate_limit_scope", None),
            rate_limit_source=getattr(final_exc, "rate_limit_source", None),
            timeout_phase=getattr(final_exc, "timeout_phase", None),
            phase_timeout_seconds=getattr(final_exc, "phase_timeout_seconds", None),
            timeout_budget_seconds=getattr(final_exc, "timeout_budget_seconds", None),
        )
        delete_staged_upload_content(upload_id)
        _mark_upload_processing_error_with_new_session(upload_id, error_message=str(final_exc))
        raise final_exc
    except SoftTimeLimitExceeded as exc:
        failed_at = utcnow_iso()
        error_message = (
            "Tempo limite da task excedido durante o processamento do upload. "
            f"soft_time_limit={settings.celery_task_soft_time_limit_seconds}s, "
            f"time_limit={settings.celery_task_time_limit_seconds}s."
        )
        log_observability_event(
            logger,
            "upload_processing_soft_time_limit_exceeded",
            level=logging.ERROR,
            upload_id=upload_id,
            task_id=task_id,
            started_at=started_at,
            failed_at=failed_at,
            total_latency_ms=elapsed_ms(task_started),
            task_attempt=task_attempt,
            retry_count=retry_count,
            soft_time_limit_seconds=settings.celery_task_soft_time_limit_seconds,
            time_limit_seconds=settings.celery_task_time_limit_seconds,
            exception_class=exc.__class__.__name__,
            error_message=error_message,
        )
        delete_staged_upload_content(upload_id)
        _mark_upload_processing_error_with_new_session(upload_id, error_message=error_message)
        raise RuntimeError(error_message) from exc
    except Exception as exc:
        failed_at = utcnow_iso()
        log_observability_event(
            logger,
            "upload_processing_failed",
            level=logging.ERROR,
            upload_id=upload_id,
            task_id=task_id,
            started_at=started_at,
            failed_at=failed_at,
            total_latency_ms=elapsed_ms(task_started),
            task_attempt=task_attempt,
            retry_count=retry_count,
            soft_time_limit_seconds=settings.celery_task_soft_time_limit_seconds,
            time_limit_seconds=settings.celery_task_time_limit_seconds,
            exception_class=exc.__class__.__name__,
            error_message=str(exc),
        )
        delete_staged_upload_content(upload_id)
        _mark_upload_processing_error_with_new_session(upload_id, error_message=str(exc))
        raise
