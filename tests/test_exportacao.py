from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from io import StringIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models.anomalia import Anomalia
from backend.app.models.audit_log import AuditLog
from backend.app.models.documento import Documento
from backend.app.models.upload import Upload


def _seed_export_data(db_session, extra_anomalias: list[dict[str, object]] | None = None) -> None:
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
            criado_em=datetime(2026, 4, 15, 9, 30, tzinfo=timezone.utc),
        )
    )
    for anomalia in extra_anomalias or []:
        db_session.add(
            Anomalia(
                documento_id=documento.id,
                codigo=str(anomalia["codigo"]),
                descricao=str(anomalia["descricao"]),
                severidade=str(anomalia["severidade"]),
                criado_em=anomalia["criado_em"],
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


def _read_xlsx_xml_files(content: bytes) -> str:
    with ZipFile(BytesIO(content)) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xml")
        )


def _read_csv_rows(content: bytes) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(content.decode("utf-8-sig")), delimiter=";")
    return list(reader)


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


@pytest.mark.parametrize(
    ("path", "expected_format"),
    [
        ("/api/v1/exportar/csv", "csv"),
        ("/api/v1/exportar/excel", "excel"),
    ],
)
def test_exportacao_documentos_limpa_logs_anteriores_e_registra_apenas_exportacao_atual(
    db_session, path: str, expected_format: str
) -> None:
    _seed_export_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        with TestClient(app) as client:
            response = client.get(path)
    finally:
        app.dependency_overrides.clear()

    remaining_logs = db_session.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc())).all()

    assert response.status_code == 200
    assert len(remaining_logs) == 1
    assert remaining_logs[0].evento == "exportacao_realizada"
    assert remaining_logs[0].entidade_tipo == "documentos"
    assert remaining_logs[0].payload == {
        "formato": expected_format,
        "quantidade_registros": 1,
    }


def test_exportacao_excel_inclui_snapshot_do_log_de_auditoria(db_session) -> None:
    _seed_export_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/exportar/excel")
    finally:
        app.dependency_overrides.clear()

    workbook_xml = _read_xlsx_xml_files(response.content)

    assert response.status_code == 200
    assert "Log Auditoria" in workbook_xml
    assert "upload_realizado" in workbook_xml
    assert "qa@test.local" in workbook_xml


@pytest.mark.parametrize(
    ("path", "expected_timestamp"),
    [
        ("/api/v1/exportar/csv", "2026-04-15 12:30:00+03:00"),
        ("/api/v1/exportar/excel", "2026-04-15 12:30:00+03:00"),
    ],
)
def test_exportacao_documentos_formata_flag_detectada_em_em_gmt_mais_tres(
    db_session, path: str, expected_timestamp: str
) -> None:
    _seed_export_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        with TestClient(app) as client:
            response = client.get(path)
    finally:
        app.dependency_overrides.clear()

    if path.endswith("/csv"):
        exported_content = response.content.decode("utf-8-sig")
    else:
        exported_content = _read_xlsx_xml_files(response.content)

    assert response.status_code == 200
    assert expected_timestamp in exported_content


def test_exportacao_csv_consolida_multiplas_flags_no_mesmo_registro(db_session) -> None:
    _seed_export_data(
        db_session,
        extra_anomalias=[
            {
                "codigo": "DATA_EMISSAO_INV",
                "descricao": "Data de emissao posterior ao pagamento.",
                "severidade": "CRITICA",
                "criado_em": datetime(2026, 4, 15, 11, 0, tzinfo=timezone.utc),
            }
        ],
    )
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/exportar/csv")
    finally:
        app.dependency_overrides.clear()

    rows = _read_csv_rows(response.content)

    assert response.status_code == 200
    assert len(rows) == 1
    assert rows[0]["Flag Codigo"] == "APROVADOR_NOK | DATA_EMISSAO_INV"
    assert (
        rows[0]["Flag Descricao"]
        == "Aprovador nao consta na lista autorizada. | Data de emissao posterior ao pagamento."
    )
    assert rows[0]["Flag Severidade"] == "ALTA | CRITICA"
    assert rows[0]["Flag Detectada Em"] == "2026-04-15 12:30:00+03:00 | 2026-04-15 14:00:00+03:00"


def test_exportacao_excel_consolida_multiplas_flags_no_mesmo_registro(db_session) -> None:
    _seed_export_data(
        db_session,
        extra_anomalias=[
            {
                "codigo": "DATA_EMISSAO_INV",
                "descricao": "Data de emissao posterior ao pagamento.",
                "severidade": "CRITICA",
                "criado_em": datetime(2026, 4, 15, 11, 0, tzinfo=timezone.utc),
            }
        ],
    )
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/exportar/excel")
    finally:
        app.dependency_overrides.clear()

    workbook_xml = _read_xlsx_xml_files(response.content)

    assert response.status_code == 200
    assert "APROVADOR_NOK | DATA_EMISSAO_INV" in workbook_xml
    assert (
        "Aprovador nao consta na lista autorizada. | Data de emissao posterior ao pagamento."
        in workbook_xml
    )
    assert "ALTA | CRITICA" in workbook_xml
    assert "2026-04-15 12:30:00+03:00 | 2026-04-15 14:00:00+03:00" in workbook_xml
