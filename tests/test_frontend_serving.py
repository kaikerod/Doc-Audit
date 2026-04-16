from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


def test_root_serves_frontend_dashboard() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "DocAudit" in response.text
    assert 'src="js/app.js"' in response.text
