from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models.upload import Upload
from backend.app.routers.uploads import get_upload_storage_dir


@pytest.fixture()
def upload_storage_dir() -> Path:
    temp_dir = Path(tempfile.mkdtemp())
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_upload_txt_valido_returns_200(
    db_session, upload_storage_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_upload_storage_dir] = lambda: upload_storage_dir
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: len(data))

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
