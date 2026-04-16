from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models.anomalia import Anomalia
from backend.app.models.documento import Documento
from backend.app.models.upload import Upload


def test_list_documentos_returns_real_items_from_uploads_and_documentos(db_session) -> None:
    upload_processando = Upload(
        nome_arquivo="nf-pendente.txt",
        caminho_arquivo="C:/tmp/nf-pendente.txt",
        hash_sha256="a" * 64,
        tamanho_bytes=120,
        status="pendente",
    )
    upload_concluido = Upload(
        nome_arquivo="nf-concluida.txt",
        caminho_arquivo="C:/tmp/nf-concluida.txt",
        hash_sha256="b" * 64,
        tamanho_bytes=240,
        status="concluído",
    )
    db_session.add_all([upload_processando, upload_concluido])
    db_session.commit()
    db_session.refresh(upload_processando)
    db_session.refresh(upload_concluido)

    documento = Documento(
        upload_id=upload_concluido.id,
        numero_nf="NF-2026-900",
        cnpj_emitente="11.222.333/0001-81",
        data_emissao=date(2026, 4, 15),
        data_pagamento=date(2026, 4, 16),
        valor_total=Decimal("1500.00"),
        aprovador="Maria Silva",
        descricao="Servico de suporte",
        status_extracao="concluído",
    )
    db_session.add(documento)
    db_session.commit()
    db_session.refresh(documento)

    anomalia = Anomalia(
        documento_id=documento.id,
        codigo="VALOR_ZERO",
        descricao="Valor total da NF e zero ou negativo.",
        severidade="ALTA",
    )
    db_session.add(anomalia)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/documentos")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2

    concluded_item = next(item for item in payload["items"] if item["nome_arquivo"] == "nf-concluida.txt")
    pending_item = next(item for item in payload["items"] if item["nome_arquivo"] == "nf-pendente.txt")

    assert concluded_item["numero_nf"] == "NF-2026-900"
    assert concluded_item["status"] == "concluído"
    assert concluded_item["flags"][0]["codigo"] == "VALOR_ZERO"
    assert pending_item["documento_id"] is None
    assert pending_item["status"] == "pendente"
    assert pending_item["flags"] == []
