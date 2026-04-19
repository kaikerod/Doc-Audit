from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app


def test_health_reports_limited_mode_without_openrouter_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr("backend.app.main.build_queue_health_check", lambda: ("ok", True, None))

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
            "queue": "ok",
        },
        "features": {
            "uploads_enabled": False,
            "upload_max_files": settings.upload_max_files,
            "upload_max_size_bytes": settings.upload_max_size_bytes,
            "processing_mode": settings.processing_mode,
        },
        "detail": "OPENROUTER_API_KEY nao configurada. Configure a integracao de IA para habilitar uploads.",
    }


def test_health_reports_uploads_enabled_when_openrouter_key_exists(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr("backend.app.main.build_ai_health_check", lambda: ("ok", True, None))
    monkeypatch.setattr("backend.app.main.build_queue_health_check", lambda: ("ok", True, None))

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
            "queue": "ok",
        },
        "features": {
            "uploads_enabled": True,
            "upload_max_files": settings.upload_max_files,
            "upload_max_size_bytes": settings.upload_max_size_bytes,
            "processing_mode": settings.processing_mode,
        },
    }


def test_health_reports_limited_mode_when_openrouter_is_unreachable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(
        "backend.app.main.build_ai_health_check",
        lambda: (
            "unreachable",
            False,
            "Falha ao conectar ao OpenRouter. Verifique rede, DNS e firewall do backend.",
        ),
    )
    monkeypatch.setattr("backend.app.main.build_queue_health_check", lambda: ("ok", True, None))

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
            "queue": "ok",
        },
        "features": {
            "uploads_enabled": False,
            "upload_max_files": settings.upload_max_files,
            "upload_max_size_bytes": settings.upload_max_size_bytes,
            "processing_mode": settings.processing_mode,
        },
        "detail": "Falha ao conectar ao OpenRouter. Verifique rede, DNS e firewall do backend.",
    }


def test_health_reports_limited_mode_when_queue_is_unreachable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr("backend.app.main.build_ai_health_check", lambda: ("ok", True, None))
    monkeypatch.setattr(
        "backend.app.main.build_queue_health_check",
        lambda: (
            "unreachable",
            False,
            "Falha ao conectar ao Redis. Verifique a fila de processamento e o worker.",
        ),
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
            "ai": "ok",
            "queue": "unreachable",
        },
        "features": {
            "uploads_enabled": False,
            "upload_max_files": settings.upload_max_files,
            "upload_max_size_bytes": settings.upload_max_size_bytes,
            "processing_mode": settings.processing_mode,
        },
        "detail": "Falha ao conectar ao Redis. Verifique a fila de processamento e o worker.",
    }
