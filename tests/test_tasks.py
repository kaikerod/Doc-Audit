from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from backend.app.models.audit_log import AuditLog
from backend.app.models.documento import Documento
from backend.app.models.upload import Upload
from backend.app.schemas.documento import DocumentExtractionResult
from backend.app.workers.tasks import celery_app, process_upload_document


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

    with patch("backend.app.workers.tasks.SessionLocal", return_value=db_session), patch(
        "backend.app.workers.tasks.Path.read_text", return_value="conteudo fiscal"
    ), patch(
        "backend.app.workers.tasks.extract_document_data", return_value=extraction_result
    ):
        result = process_upload_document.delay(str(upload.id))

    celery_app.conf.update(
        task_always_eager=original_always_eager,
        task_eager_propagates=original_eager_propagates,
        broker_url=original_broker_url,
        result_backend=original_result_backend,
    )

    documento = db_session.scalar(select(Documento).where(Documento.upload_id == upload.id))
    upload = db_session.get(Upload, upload.id)
    audit_logs = db_session.scalars(select(AuditLog)).all()

    assert result.successful()
    assert documento is not None
    assert documento.status_extracao == "concluído"
    assert documento.numero_nf == "NF-2026-001"
    assert upload is not None
    assert upload.status == "concluído"
    assert len(documento.anomalias) == 1
    assert documento.anomalias[0].codigo == "VALOR_ZERO"
    assert {log.evento for log in audit_logs} == {
        "processamento_iniciado",
        "anomalias_detectadas",
        "processamento_concluido",
    }
