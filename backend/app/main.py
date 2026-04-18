from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import Base, engine
from .routers.documentos import router as documentos_router
from .routers.exportar import router as exportar_router
from .routers.uploads import router as uploads_router
from .services.ia_service import build_ai_health_check
from .services.queue_service import build_queue_health_check

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
FAVICON_PATH = FRONTEND_DIR / "favicon.svg"

tags_metadata = [
    {
        "name": "uploads",
        "description": "Gerenciamento de entrada de arquivos TXT e validações iniciais.",
    },
    {
        "name": "documentos",
        "description": "Consulta e listagem dos documentos processados pela IA e suas respectivas anomalias.",
    },
    {
        "name": "exportacao",
        "description": "Geração de relatórios em CSV e Excel para auditoria externa.",
    },
    {
        "name": "health",
        "description": "Endpoints de monitoramento de integridade da API e banco de dados.",
    },
    {
        "name": "meta",
        "description": "Informações básicas sobre a aplicação.",
    },
]

app = FastAPI(
    title=settings.app_name,
    description="Sistema de Análise e Auditoria de Documentos Fiscais com IA. Esta API permite o envio de arquivos TXT, extração de dados via IA e detecção de anomalias.",
    version=settings.app_version,
    contact={
        "name": "DocAudit Support",
        "email": "support@docaudit.local",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(uploads_router)
app.include_router(documentos_router)
app.include_router(exportar_router)

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="frontend-css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="frontend-js")


@app.on_event("startup")
def initialize_database_schema() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/", tags=["meta"], response_model=None)
def read_root() -> Response:
    if FRONTEND_DIR.exists():
        return FileResponse(FRONTEND_DIR / "index.html")

    return JSONResponse({"name": settings.app_name, "version": settings.app_version})


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def serve_favicon() -> Response:
    if FAVICON_PATH.exists():
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

    return Response(status_code=204)


@app.get(f"{settings.api_v1_prefix}/health/live", tags=["health"])
def liveness_check() -> dict[str, str]:
    return {"status": "alive", "app": settings.app_name}


@app.get(f"{settings.api_v1_prefix}/health", tags=["health"])
def readiness_check() -> JSONResponse:
    ai_status, uploads_enabled, ai_detail = build_ai_health_check()
    queue_status, queue_enabled, queue_detail = build_queue_health_check()

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        detail_parts = [str(exc)]
        if ai_detail:
            detail_parts.append(ai_detail)
        if queue_detail:
            detail_parts.append(queue_detail)

        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "app": settings.app_name,
                "checks": {
                    "api": "ok",
                    "database": "error",
                    "ai": ai_status,
                    "queue": queue_status,
                },
                "features": {
                    "uploads_enabled": False,
                },
                "detail": " ".join(detail_parts),
            },
        )

    uploads_enabled = uploads_enabled and queue_enabled
    content = {
        "status": "ok" if uploads_enabled else "limited",
        "app": settings.app_name,
        "checks": {
            "api": "ok",
            "database": "ok",
            "ai": ai_status,
            "queue": queue_status,
        },
        "features": {
            "uploads_enabled": uploads_enabled,
        },
    }

    detail_parts = [detail for detail in (ai_detail, queue_detail) if detail]
    if detail_parts:
        content["detail"] = " ".join(detail_parts)

    return JSONResponse(
        status_code=200,
        content=content,
    )
