from __future__ import annotations

from hashlib import sha256
from unittest.mock import patch

from celery.exceptions import Retry, SoftTimeLimitExceeded
import pytest

from sqlalchemy import select

from backend.app.config import settings
from backend.app.models.audit_log import AuditLog
from backend.app.models.documento import Documento
from backend.app.models.upload import Upload
from backend.app.schemas.documento import DocumentExtractionResult
from backend.app.services.ia_service import OpenRouterTimeoutError, OpenRouterUpstreamError
from backend.app.workers.tasks import celery_app, process_upload_document


def test_celery_worker_prefetch_multiplier_is_one() -> None:
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_process_upload_document_task_time_limits_are_configured() -> None:
    assert celery_app.conf.task_soft_time_limit == settings.celery_task_soft_time_limit_seconds
    assert celery_app.conf.task_time_limit == settings.celery_task_time_limit_seconds
    assert process_upload_document.soft_time_limit == settings.celery_task_soft_time_limit_seconds
    assert process_upload_document.time_limit == settings.celery_task_time_limit_seconds


def test_process_upload_document_task_fluxo_completo_eager(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-teste.txt",
        caminho_arquivo="C:/fake/nf-teste.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    extraction_result = DocumentExtractionResult(
        numero_nf="NF-2026-001",
        cnpj_emitente="11.222.333/0001-81",
        cnpj_destinatario="45.723.174/0001-10",
        data_emissao="2026-04-15",
        data_pagamento="2026-04-16",
        valor_total="0",
        aprovador="Maria Silva",
        descricao="Servico mensal",
        confiancas={
            "numero_nf": 0.99,
            "cnpj_emitente": 0.98,
            "cnpj_destinatario": 0.97,
            "data_emissao": 0.96,
            "data_pagamento": 0.95,
            "valor_total": 0.94,
            "aprovador": 0.93,
            "descricao": 0.92,
        },
        extraction_failed_fields=[],
    )

    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates
    original_broker_url = celery_app.conf.broker_url
    original_result_backend = celery_app.conf.result_backend
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )

    extract_session_call_counts: list[int] = []

    with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
        "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
    ), patch(
        "backend.app.workers.tasks.extract_document_data",
        side_effect=lambda *args, **kwargs: (
            extract_session_call_counts.append(session_local_mock.call_count) or extraction_result
        ),
    ) as extract_mock:
        result = process_upload_document.delay(str(upload_id))

    celery_app.conf.update(
        task_always_eager=original_always_eager,
        task_eager_propagates=original_eager_propagates,
        broker_url=original_broker_url,
        result_backend=original_result_backend,
    )

    documento = db_session.scalar(select(Documento).where(Documento.upload_id == upload_id))
    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert result.successful()
    assert documento is not None
    assert documento.status_extracao == "concluido"
    assert documento.numero_nf == "NF-2026-001"
    assert upload is not None
    assert upload.status == "concluido"
    assert len(documento.anomalias) == 1
    assert documento.anomalias[0].codigo == "VALOR_ZERO"
    assert extract_session_call_counts == [1]
    assert session_local_mock.call_count == 2
    assert extract_mock.call_args.kwargs["request_context"]["upload_id"] == str(upload_id)
    assert extract_mock.call_args.kwargs["request_context"]["task_id"]
    assert {log.evento for log in audit_logs} == {
        "processamento_iniciado",
        "anomalias_detectadas",
        "processamento_concluido",
    }


def test_process_upload_document_marks_upload_as_error_on_processing_failure(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-falha.txt",
        caminho_arquivo="C:/fake/nf-falha.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates
    original_broker_url = celery_app.conf.broker_url
    original_result_backend = celery_app.conf.result_backend
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=False,
        broker_url="memory://",
        result_backend="cache+memory://",
    )

    with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
        "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
    ), patch(
        "backend.app.workers.tasks.extract_document_data",
        side_effect=RuntimeError("OpenRouter indisponivel"),
    ):
        result = process_upload_document.delay(str(upload_id))

    celery_app.conf.update(
        task_always_eager=original_always_eager,
        task_eager_propagates=original_eager_propagates,
        broker_url=original_broker_url,
        result_backend=original_result_backend,
    )

    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert result.failed()
    assert upload is not None
    assert upload.status == "erro"
    assert db_session.scalar(select(Documento)) is None
    assert session_local_mock.call_count == 2
    assert {log.evento for log in audit_logs} == {
        "processamento_iniciado",
        "processamento_erro",
    }


def test_process_upload_document_schedules_retry_for_transient_ia_errors(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-timeout.txt",
        caminho_arquivo="C:/fake/nf-timeout.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
        "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
    ), patch(
        "backend.app.workers.tasks.extract_document_data",
        side_effect=OpenRouterTimeoutError("Timeout ao chamar OpenRouter."),
    ), patch.object(process_upload_document, "retry", side_effect=Retry()) as retry_mock:
        with pytest.raises(Retry):
            process_upload_document.run(str(upload_id))

    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert upload is not None
    assert upload.status == "processando"
    assert db_session.scalar(select(Documento)) is None
    assert [log.evento for log in audit_logs] == ["processamento_iniciado"]
    assert retry_mock.call_count == 1
    assert retry_mock.call_args.kwargs["countdown"] == 1.0
    assert retry_mock.call_args.kwargs["kwargs"]["countdown_seconds"] == 1.0
    assert retry_mock.call_args.kwargs["kwargs"]["queued_at"]
    assert retry_mock.call_args.kwargs["max_retries"] == 2
    assert session_local_mock.call_count == 1


def test_process_upload_document_uses_rate_limit_retry_budget_for_429_errors(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-rate-limit.txt",
        caminho_arquivo="C:/fake/nf-rate-limit.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    original_request_id = getattr(process_upload_document.request, "id", None)
    process_upload_document.request.id = "task-rate-limit"

    try:
        with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
            "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
        ), patch(
            "backend.app.workers.tasks.extract_document_data",
            side_effect=OpenRouterUpstreamError(
                "O provedor de IA atingiu o limite de requisicoes no momento. Aguarde alguns segundos e tente novamente.",
                status_code=429,
                retryable=True,
                retry_after_seconds=1.5,
                rate_limit_scope="openrouter:test-model",
                rate_limit_source="local_cooldown",
            ),
        ), patch.object(process_upload_document, "retry", side_effect=Retry()) as retry_mock:
            with pytest.raises(Retry):
                process_upload_document.run(str(upload_id))
    finally:
        process_upload_document.request.id = original_request_id

    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert upload is not None
    assert upload.status == "processando"
    assert db_session.scalar(select(Documento)) is None
    assert [log.evento for log in audit_logs] == ["processamento_iniciado"]
    assert retry_mock.call_count == 1
    assert retry_mock.call_args.kwargs["countdown"] >= 1.5
    assert retry_mock.call_args.kwargs["kwargs"]["countdown_seconds"] >= 1.5
    assert retry_mock.call_args.kwargs["kwargs"]["queued_at"]
    assert retry_mock.call_args.kwargs["max_retries"] == settings.openrouter_rate_limit_retries
    assert session_local_mock.call_count == 1


def test_process_upload_document_marks_error_for_non_retryable_rate_limit_errors(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-rate-limit-quota.txt",
        caminho_arquivo="C:/fake/nf-rate-limit-quota.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    quota_error = OpenRouterUpstreamError(
        "A cota do modelo configurado na OpenRouter foi esgotada. Altere OPENROUTER_MODEL para outro modelo ou adicione creditos na conta.",
        status_code=429,
        retryable=False,
    )

    with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
        "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
    ), patch(
        "backend.app.workers.tasks.extract_document_data",
        side_effect=quota_error,
    ), patch.object(process_upload_document, "retry") as retry_mock:
        with pytest.raises(OpenRouterUpstreamError) as exc_info:
            process_upload_document.run(str(upload_id))

    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert str(exc_info.value) == str(quota_error)
    assert upload is not None
    assert upload.status == "erro"
    assert db_session.scalar(select(Documento)) is None
    assert session_local_mock.call_count == 2
    assert {log.evento for log in audit_logs} == {
        "processamento_iniciado",
        "processamento_erro",
    }
    retry_mock.assert_not_called()


def test_process_upload_document_marks_error_after_retry_budget_is_exhausted(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-timeout-final.txt",
        caminho_arquivo="C:/fake/nf-timeout-final.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    original_retries = process_upload_document.request.retries
    process_upload_document.request.retries = 2

    try:
        with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
            "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
        ), patch(
            "backend.app.workers.tasks.extract_document_data",
            side_effect=OpenRouterTimeoutError("Timeout ao chamar OpenRouter."),
        ), patch.object(process_upload_document, "retry") as retry_mock:
            with pytest.raises(OpenRouterTimeoutError) as exc_info:
                process_upload_document.run(str(upload_id))
    finally:
        process_upload_document.request.retries = original_retries

    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert str(exc_info.value) == "Timeout ao chamar OpenRouter apos 3 tentativas."
    assert upload is not None
    assert upload.status == "erro"
    assert db_session.scalar(select(Documento)) is None
    assert session_local_mock.call_count == 2
    assert {log.evento for log in audit_logs} == {
        "processamento_iniciado",
        "processamento_erro",
    }
    retry_mock.assert_not_called()


def test_process_upload_document_marks_upload_as_error_on_soft_time_limit(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-soft-limit.txt",
        caminho_arquivo="C:/fake/nf-soft-limit.txt",
        hash_sha256=sha256(b"conteudo fiscal").hexdigest(),
        tamanho_bytes=len(b"conteudo fiscal"),
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)
    upload_id = upload.id

    with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session) as session_local_mock, patch(
        "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
    ), patch(
        "backend.app.workers.tasks.extract_document_data",
        side_effect=SoftTimeLimitExceeded(),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            process_upload_document.run(str(upload_id))

    upload = db_session.get(Upload, upload_id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert "Tempo limite da task excedido" in str(exc_info.value)
    assert upload is not None
    assert upload.status == "erro"
    assert db_session.scalar(select(Documento)) is None
    assert session_local_mock.call_count == 2
    assert {log.evento for log in audit_logs} == {
        "processamento_iniciado",
        "processamento_erro",
    }
