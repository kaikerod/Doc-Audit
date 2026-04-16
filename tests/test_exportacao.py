from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models.anomalia import Anomalia
from backend.app.models.audit_log import AuditLog
from backend.app.models.documento import Documento
from backend.app.models.upload import Upload


def _seed_export_data(db_session) -> None:
    upload = Upload(
        nome_arquivo="nf-exportacao.txt",
        caminho_arquivo="C:/tmp/nf-exportacao.txt",
        hash_sha256="c" * 64,
        tamanho_bytes=512,
        status="concluido",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)

    documento = Documento(
        upload_id=upload.id,
        numero_nf="NF-2026-321",
        cnpj_emitente="11.222.333/0001-81",
        cnpj_destinatario="45.723.174/0001-10",
        data_emissao=date(2026, 4, 15),
        data_pagamento=date(2026, 4, 16),
        valor_total=Decimal("2450.90"),
        aprovador="Maria Silva",
        descricao="Servico de auditoria",
        status_extracao="concluido",
    )
    db_session.add(documento)
    db_session.commit()
    db_session.refresh(documento)

    db_session.add(
        Anomalia(
            documento_id=documento.id,
            codigo="APROVADOR_NOK",
            descricao="Aprovador nao consta na lista autorizada.",
            severidade="ALTA",
        )
    )
    db_session.add(
        AuditLog(
            id=uuid4(),
            evento="upload_realizado",
            entidade_tipo="upload",
            entidade_id=str(upload.id),
            usuario="qa@test.local",
            ip="127.0.0.1",
            payload={"arquivo": upload.nome_arquivo},
        )
    )
    db_session.commit()


@pytest.mark.parametrize(
    ("path", "expected_extension", "expected_prefix"),
    [
        ("/api/v1/exportar/csv", ".csv", b"\xef\xbb\xbf"),
        ("/api/v1/exportar/excel", ".xlsx", b"PK"),
        ("/api/v1/exportar/log", ".csv", b"\xef\xbb\xbf"),
        ("/api/v1/exportar/log?formato=excel", ".xlsx", b"PK"),
    ],
)
def test_rotas_exportacao_retorna_attachment_com_extensao_correta(
    db_session, path: str, expected_extension: str, expected_prefix: bytes
) -> None:
    _seed_export_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        with TestClient(app) as client:
            response = client.get(path)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("attachment;")
    assert expected_extension in content_disposition
    assert response.content.startswith(expected_prefix)
