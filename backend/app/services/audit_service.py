from __future__ import annotations

from typing import Any

from ..database import DbSession
from ..models.audit_log import AuditLog


def log_audit_event(
    db: DbSession,
    *,
    evento: str,
    entidade_tipo: str | None = None,
    entidade_id: str | None = None,
    usuario: str | None = None,
    ip: str | None = None,
    payload: dict[str, Any] | list[Any] | None = None,
) -> AuditLog:
    """Persiste um evento de auditoria e retorna o registro criado."""
    audit_log = AuditLog(
        evento=evento,
        entidade_tipo=entidade_tipo,
        entidade_id=entidade_id,
        usuario=usuario,
        ip=ip,
        payload=payload,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log
