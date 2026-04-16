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

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title=settings.app_name, version=settings.app_version)
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
def initialize_local_sqlite() -> None:
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)


@app.get("/", tags=["meta"], response_model=None)
def read_root() -> Response:
    if FRONTEND_DIR.exists():
        return FileResponse(FRONTEND_DIR / "index.html")

    return JSONResponse({"name": settings.app_name, "version": settings.app_version})


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
