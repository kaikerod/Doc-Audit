from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from io import StringIO
from uuid import uuid4
import xml.etree.ElementTree as ET
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

XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XLSX_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


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


def _read_xlsx_rows(content: bytes, sheet_name: str) -> list[dict[str, str]]:
    with ZipFile(BytesIO(content)) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationships = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships_root.findall(f"{{{XLSX_REL_NS}}}Relationship")
        }
        worksheet_target = None
        for sheet in workbook_root.findall(f".//{{{XLSX_MAIN_NS}}}sheet"):
            if sheet.attrib.get("name") != sheet_name:
                continue
            relation_id = sheet.attrib.get(f"{{{XLSX_DOC_REL_NS}}}id")
            worksheet_target = relationships.get(relation_id)
            break

        if worksheet_target is None:
            raise KeyError(f"Aba XLSX nao encontrada: {sheet_name}")

        worksheet_root = ET.fromstring(archive.read(f"xl/{worksheet_target}"))
        sheet_rows = []
        for row in worksheet_root.findall(f".//{{{XLSX_MAIN_NS}}}sheetData/{{{XLSX_MAIN_NS}}}row"):
            values = []
            for cell in row.findall(f"{{{XLSX_MAIN_NS}}}c"):
                text_node = cell.find(f"{{{XLSX_MAIN_NS}}}is/{{{XLSX_MAIN_NS}}}t")
                values.append(text_node.text if text_node is not None and text_node.text is not None else "")
            sheet_rows.append(values)

    headers = [str(value) if value is not None else "" for value in sheet_rows[0]]
    return [
        {
            header: "" if row[index] is None else str(row[index])
            for index, header in enumerate(headers)
        }
        for row in sheet_rows[1:]
    ]


def _read_xlsx_sheet_names(content: bytes) -> list[str]:
    with ZipFile(BytesIO(content)) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    return [sheet.attrib["name"] for sheet in workbook_root.findall(f".//{{{XLSX_MAIN_NS}}}sheet")]


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

    sheet_names = _read_xlsx_sheet_names(response.content)
    log_rows = _read_xlsx_rows(response.content, "Log Auditoria")

    assert response.status_code == 200
    assert "Log Auditoria" in sheet_names
    assert len(log_rows) == 1
    assert log_rows[0]["evento"] == "upload_realizado"
    assert log_rows[0]["usuario"] == "qa@test.local"


@pytest.mark.parametrize(
    ("path", "expected_timestamp"),
    [
        ("/api/v1/exportar/csv", "15/04/2026 06:30:00"),
        ("/api/v1/exportar/excel", "15/04/2026 06:30:00"),
    ],
)
def test_exportacao_documentos_formata_data_hora_em_brasilia(
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
        exported_content = _read_csv_rows(response.content)[0]["anomalia_detectada_em"]
    else:
        exported_content = _read_xlsx_rows(response.content, "Documentos")[0]["anomalia_detectada_em"]

    assert response.status_code == 200
    assert exported_content == expected_timestamp


def test_exportacao_csv_usa_modelo_analitico_para_power_bi(db_session) -> None:
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
    assert len(rows) == 2
    assert list(rows[0].keys())[:10] == [
        "upload_id",
        "upload_criado_em",
        "upload_status",
        "nome_arquivo",
        "tamanho_bytes",
        "documento_id",
        "documento_criado_em",
        "possui_documento",
        "documento_status",
        "tipo_registro",
    ]
    assert {row["anomalia_codigo"] for row in rows} == {
        "APROVADOR_NOK",
        "DATA_EMISSAO_INV",
    }
    assert {row["anomalia_severidade"] for row in rows} == {"ALTA", "CRITICA"}
    assert {row["anomalia_detectada_em"] for row in rows} == {
        "15/04/2026 06:30:00",
        "15/04/2026 08:00:00",
    }
    for row in rows:
        assert row["tipo_registro"] == "documento_com_anomalia"
        assert row["data_emissao"] == "15/04/2026"
        assert row["data_pagamento"] == "16/04/2026"
        assert row["emissao_competencia"] == "2026-04"
        assert row["pagamento_competencia"] == "2026-04"
        assert row["possui_documento"] == "1"
        assert row["possui_anomalia"] == "1"
        assert row["quantidade_anomalias"] == "2"
        assert row["quantidade_anomalias_critica"] == "1"
        assert row["quantidade_anomalias_alta"] == "1"
        assert row["quantidade_anomalias_media"] == "0"
        assert row["severidade_maxima"] == "CRITICA"


def test_exportacao_excel_usa_modelo_analitico_para_power_bi(db_session) -> None:
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

    rows = _read_xlsx_rows(response.content, "Documentos")

    assert response.status_code == 200
    assert len(rows) == 2
    assert {row["anomalia_codigo"] for row in rows} == {
        "APROVADOR_NOK",
        "DATA_EMISSAO_INV",
    }
    assert {row["anomalia_detectada_em"] for row in rows} == {
        "15/04/2026 06:30:00",
        "15/04/2026 08:00:00",
    }
    for row in rows:
        assert row["tipo_registro"] == "documento_com_anomalia"
        assert row["documento_status"] == "concluido"
        assert row["possui_anomalia"] == "1"
        assert row["quantidade_anomalias"] == "2"
        assert row["quantidade_anomalias_critica"] == "1"
        assert row["quantidade_anomalias_alta"] == "1"
        assert row["severidade_maxima"] == "CRITICA"
