from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import engine
from .routers.documentos import router as documentos_router
from .routers.exportar import router as exportar_router
from .routers.uploads import router as uploads_router

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(uploads_router)
app.include_router(documentos_router)
app.include_router(exportar_router)


@app.get("/", tags=["meta"])
def read_root() -> dict[str, str]:
    return {"name": settings.app_name, "version": settings.app_version}


@app.get(f"{settings.api_v1_prefix}/health/live", tags=["health"])
def liveness_check() -> dict[str, str]:
    return {"status": "alive", "app": settings.app_name}


@app.get(f"{settings.api_v1_prefix}/health", tags=["health"])
def readiness_check() -> JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "app": settings.app_name,
                "checks": {
                    "api": "ok",
                    "database": "error",
                },
                "detail": str(exc),
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "app": settings.app_name,
            "checks": {
                "api": "ok",
                "database": "ok",
            },
        },
    )
