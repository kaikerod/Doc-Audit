from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models.audit_log import AuditLog
from backend.app.models.documento import Documento
from backend.app.models.upload import Upload
from backend.app.routers.uploads import get_upload_storage_dir


@pytest.fixture()
def upload_storage_dir() -> Path:
    return Path.cwd() / "tests" / ".tmp" / "uploads"


def test_upload_txt_valido_returns_200(
    db_session, upload_storage_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: len(data))

    with patch("backend.app.routers.uploads.enqueue_upload_processing", return_value="task-1") as enqueue_mock:
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/uploads",
                    files=[("files", ("nota-fiscal.txt", b"conteudo de teste", "text/plain"))],
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["nome_arquivo"] == "nota-fiscal.txt"
    assert response_data["items"][0]["status"] == "pendente"

    saved_upload = db_session.scalar(select(Upload))
    assert saved_upload is not None
    assert saved_upload.nome_arquivo == "nota-fiscal.txt"
    assert saved_upload.status == "pendente"
    assert saved_upload.tamanho_bytes == len(b"conteudo de teste")
    assert saved_upload.caminho_arquivo.endswith(".txt")
    assert db_session.scalar(select(Documento)) is None
    enqueue_mock.assert_called_once_with(saved_upload.id, position=0)


def test_upload_marks_error_when_enqueue_fails(
    db_session, upload_storage_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir

    write_attempts: list[Path] = []
    monkeypatch.setattr(
        Path,
        "write_bytes",
        lambda self, data: write_attempts.append(Path(self)) or len(data),
    )

    with patch(
        "backend.app.routers.uploads.enqueue_upload_processing",
        side_effect=RuntimeError("Redis down"),
    ):
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/uploads",
                    files=[("files", ("nota-fiscal.txt", b"conteudo de teste", "text/plain"))],
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "erro"

    saved_upload = db_session.scalar(select(Upload))
    assert saved_upload is not None
    assert saved_upload.status == "erro"
    assert db_session.scalar(select(Documento)) is None
    assert write_attempts == [Path(saved_upload.caminho_arquivo)]

    audit_log = db_session.scalar(select(AuditLog))
    assert audit_log is not None
    assert audit_log.evento == "processamento_erro"
    assert audit_log.payload == {
        "upload_id": str(saved_upload.id),
        "arquivo": "nota-fiscal.txt",
        "erro": "Falha ao enfileirar processamento: Redis down",
    }


def test_upload_persists_error_record_when_txt_is_not_utf8(
    db_session, upload_storage_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: len(data))

    with patch("backend.app.routers.uploads.enqueue_upload_processing") as enqueue_mock:
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/uploads",
                    files=[("files", ("nota-fiscal.txt", b"\xff\xfe\x00\x00", "text/plain"))],
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "erro"

    saved_upload = db_session.scalar(select(Upload))
    assert saved_upload is not None
    assert saved_upload.status == "erro"
    assert db_session.scalar(select(Documento)) is None
    enqueue_mock.assert_not_called()

    audit_log = db_session.scalar(select(AuditLog))
    assert audit_log is not None
    assert audit_log.payload == {
        "upload_id": str(saved_upload.id),
        "arquivo": "nota-fiscal.txt",
        "erro": "Arquivo TXT precisa estar codificado em UTF-8.",
    }


def test_upload_persists_successful_and_failed_files_in_same_batch(
    db_session, upload_storage_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: len(data))

    with patch(
        "backend.app.routers.uploads.enqueue_upload_processing",
        side_effect=[
            "task-1",
            RuntimeError("Redis down"),
        ],
    ):
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/uploads",
                    files=[
                        ("files", ("nota-ok.txt", b"conteudo ok", "text/plain")),
                        ("files", ("nota-erro.txt", b"conteudo erro", "text/plain")),
                    ],
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"]] == ["pendente", "erro"]

    uploads = db_session.scalars(select(Upload).order_by(Upload.nome_arquivo.asc())).all()
    assert [upload.nome_arquivo for upload in uploads] == ["nota-erro.txt", "nota-ok.txt"]
    assert [upload.status for upload in uploads] == ["erro", "pendente"]
    assert db_session.scalar(select(Documento)) is None


def test_upload_pdf_retorna_400(db_session, upload_storage_dir: Path) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads",
                files=[("files", ("nota-fiscal.pdf", b"%PDF-1.4", "application/pdf"))],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "Apenas arquivos .txt sao permitidos."}
    assert db_session.scalar(select(Upload)) is None


def test_list_uploads_returns_paginated_items(db_session, upload_storage_dir: Path) -> None:
    upload_1 = Upload(
        nome_arquivo="nf-1.txt",
        caminho_arquivo=str(upload_storage_dir / "nf-1.txt"),
        hash_sha256="1" * 64,
        tamanho_bytes=11,
        status="pendente",
    )
    upload_2 = Upload(
        nome_arquivo="nf-2.txt",
        caminho_arquivo=str(upload_storage_dir / "nf-2.txt"),
        hash_sha256="2" * 64,
        tamanho_bytes=22,
        status="concluido",
    )
    db_session.add_all([upload_1, upload_2])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/uploads?limit=1&offset=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["nome_arquivo"] == "nf-1.txt"


def test_get_upload_returns_single_item(db_session, upload_storage_dir: Path) -> None:
    upload = Upload(
        nome_arquivo="nf-detalhe.txt",
        caminho_arquivo=str(upload_storage_dir / "nf-detalhe.txt"),
        hash_sha256="9" * 64,
        tamanho_bytes=33,
        status="pendente",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/uploads/{upload.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(upload.id)
    assert payload["nome_arquivo"] == "nf-detalhe.txt"


def test_delete_upload_returns_204_and_generates_audit_log(
    db_session, upload_storage_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_file = upload_storage_dir / "nf-para-excluir.txt"
    deleted_files: list[Path] = []

    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self: deleted_files.append(Path(self)),
    )

    upload = Upload(
        nome_arquivo="nf-para-excluir.txt",
        caminho_arquivo=str(stored_file),
        hash_sha256="c" * 64,
        tamanho_bytes=23,
        status="concluido",
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)

    documento = Documento(
        upload_id=upload.id,
        numero_nf="NF-2026-100",
        cnpj_emitente="11.222.333/0001-81",
        data_emissao=date(2026, 4, 15),
        data_pagamento=date(2026, 4, 16),
        valor_total=Decimal("1234.56"),
        status_extracao="concluido",
    )
    db_session.add(documento)
    db_session.commit()
    db_session.refresh(documento)

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/uploads/{upload.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(Upload, upload.id) is None
    assert db_session.get(Documento, documento.id) is None
    assert deleted_files == [stored_file]

    audit_log = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.evento == "EXCLUSAO_UPLOAD")
        .where(AuditLog.entidade_id == str(upload.id))
    )

    assert audit_log is not None
    assert audit_log.entidade_tipo == "upload"
    assert audit_log.payload == {
        "upload_id": str(upload.id),
        "nome_arquivo": "nf-para-excluir.txt",
        "status_upload": "concluido",
        "documentos": [
            {
                "documento_id": str(documento.id),
                "numero_nf": "NF-2026-100",
                "cnpj_emitente": "11.222.333/0001-81",
                "data_emissao": "2026-04-15",
                "data_pagamento": "2026-04-16",
                "valor_total": "1234.56",
                "status_extracao": "concluido",
            }
        ],
    }
