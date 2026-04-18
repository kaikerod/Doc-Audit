from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..config import settings
from ..schemas.observability import LoadValidationSnapshot
from ..services.load_validation_service import build_load_validation_snapshot

router = APIRouter(prefix=f"{settings.api_v1_prefix}/observability", tags=["observability"])


@router.get(
    "/load-validation",
    response_model=LoadValidationSnapshot,
    summary="Retorna um snapshot operacional para validacao de carga",
    description=(
        "Expone profundidade da fila Redis, atividade dos workers Celery e um resumo dos "
        "eventos de observabilidade recentes para diagnostico de throughput."
    ),
)
def get_load_validation_snapshot(
    since: str | None = Query(
        default=None,
        description="Filtra eventos com timestamp ISO-8601 maior ou igual ao valor informado.",
    ),
    include_events: bool = Query(
        default=False,
        description="Inclui os eventos recentes usados para compor o resumo.",
    ),
    event_limit: int = Query(
        default=200,
        ge=10,
        le=5000,
        description="Quantidade maxima de eventos recentes considerada no snapshot.",
    ),
) -> LoadValidationSnapshot:
    try:
        return build_load_validation_snapshot(
            since=since,
            include_events=include_events,
            event_limit=event_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
