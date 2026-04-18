from __future__ import annotations

from contextlib import nullcontext

from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app


def test_health_reports_limited_mode_without_openrouter_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "limited",
        "app": settings.app_name,
        "checks": {
            "api": "ok",
            "database": "ok",
            "ai": "not_configured",
        },
        "features": {
            "uploads_enabled": False,
        },
        "detail": "OPENROUTER_API_KEY nao configurada. Configure a integracao de IA para habilitar uploads.",
    }


def test_health_reports_uploads_enabled_when_openrouter_key_exists(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(
        "backend.app.services.ia_service.socket.create_connection",
        lambda *args, **kwargs: nullcontext(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": settings.app_name,
        "checks": {
            "api": "ok",
            "database": "ok",
            "ai": "ok",
        },
        "features": {
            "uploads_enabled": True,
        },
    }


def test_health_reports_limited_mode_when_openrouter_is_unreachable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    def raise_connection_error(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(
        "backend.app.services.ia_service.socket.create_connection",
        raise_connection_error,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "limited",
        "app": settings.app_name,
        "checks": {
            "api": "ok",
            "database": "ok",
            "ai": "unreachable",
        },
        "features": {
            "uploads_enabled": False,
        },
        "detail": "Falha ao conectar ao OpenRouter. Verifique rede, DNS e firewall do backend.",
    }
