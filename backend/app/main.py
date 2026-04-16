from fastapi import FastAPI

from .config import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.get("/", tags=["meta"])
def read_root() -> dict[str, str]:
    return {"name": settings.app_name, "version": settings.app_version}


@app.get(f"{settings.api_v1_prefix}/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
