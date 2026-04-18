from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


def test_root_serves_frontend_dashboard() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "DocAudit" in response.text
    assert 'href="favicon.svg"' in response.text
    assert 'src="js/app.js"' in response.text


def test_favicon_is_served_without_404() -> None:
    with TestClient(app) as client:
        response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text
