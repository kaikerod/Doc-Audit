from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from ..config import settings
from ..database import DbSession, get_db
from ..services.audit_service import log_audit_event
from ..services.export_service import (
    export_audit_log_csv,
    export_audit_log_excel,
    export_documentos_csv,
    export_documentos_excel,
)

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix=f"{settings.api_v1_prefix}/exportar", tags=["exportacao"])


def _attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _log_export_event(
    db: DbSession,
    request: Request,
    *,
    entidade_tipo: str,
    formato: str,
    total_registros: int,
) -> None:
    log_audit_event(
        db,
        evento="exportacao_realizada",
        entidade_tipo=entidade_tipo,
        usuario=None,
        ip=request.client.host if request.client else None,
        payload={
            "formato": formato,
            "quantidade_registros": total_registros,
        },
    )


@router.get("/csv")
def exportar_csv(
    request: Request,
    somente_com_anomalias: bool = Query(default=False),
    db: DbSession = Depends(get_db),
) -> Response:
    export_file = export_documentos_csv(db, somente_com_anomalias=somente_com_anomalias)
    _log_export_event(
        db,
        request,
        entidade_tipo="documentos",
        formato="csv",
        total_registros=export_file.total_registros,
    )
    return Response(
        content=export_file.content,
        media_type=CSV_MEDIA_TYPE,
        headers=_attachment_headers("docaudit_exportacao.csv"),
    )


@router.get("/excel")
def exportar_excel(
    request: Request,
    somente_com_anomalias: bool = Query(default=False),
    db: DbSession = Depends(get_db),
) -> Response:
    export_file = export_documentos_excel(db, somente_com_anomalias=somente_com_anomalias)
    _log_export_event(
        db,
        request,
        entidade_tipo="documentos",
        formato="excel",
        total_registros=export_file.total_registros,
    )
    return Response(
        content=export_file.content,
        media_type=XLSX_MEDIA_TYPE,
        headers=_attachment_headers("docaudit_exportacao.xlsx"),
    )


@router.get("/log")
def exportar_log_auditoria(
    request: Request,
    formato: Literal["csv", "excel"] = Query(default="csv"),
    db: DbSession = Depends(get_db),
) -> Response:
    if formato == "excel":
        export_file = export_audit_log_excel(db)
        filename = "docaudit_log_auditoria.xlsx"
        media_type = XLSX_MEDIA_TYPE
    else:
        export_file = export_audit_log_csv(db)
        filename = "docaudit_log_auditoria.csv"
        media_type = CSV_MEDIA_TYPE

    _log_export_event(
        db,
        request,
        entidade_tipo="audit_log",
        formato=formato,
        total_registros=export_file.total_registros,
    )
    return Response(
        content=export_file.content,
        media_type=media_type,
        headers=_attachment_headers(filename),
    )
