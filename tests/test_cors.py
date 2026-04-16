from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


def test_api_accepts_requests_from_file_origin() -> None:
    with TestClient(app) as client:
        response = client.get("/", headers={"Origin": "null"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "null"


def test_api_replies_to_local_preflight_requests() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/uploads",
            headers={
                "Origin": "http://127.0.0.1:5500",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5500"
