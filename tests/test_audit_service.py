from __future__ import annotations

from sqlalchemy import select

from backend.app.models.audit_log import AuditLog
from backend.app.services.audit_service import log_audit_event


def test_log_audit_event_persists_record(db_session) -> None:
    payload = {
        "arquivo": "nota-fiscal-001.txt",
        "hash_sha256": "abc123",
        "status": "processado",
    }

    created_log = log_audit_event(
        db_session,
        evento="upload_realizado",
        entidade_tipo="upload",
        entidade_id="upload-123",
        usuario="qa@test.local",
        ip="127.0.0.1",
        payload=payload,
    )

    persisted_log = db_session.scalar(
        select(AuditLog).where(AuditLog.id == created_log.id)
    )

    assert persisted_log is not None
    assert persisted_log.id == created_log.id
    assert persisted_log.evento == "upload_realizado"
    assert persisted_log.entidade_tipo == "upload"
    assert persisted_log.entidade_id == "upload-123"
    assert persisted_log.usuario == "qa@test.local"
    assert persisted_log.ip == "127.0.0.1"
    assert persisted_log.payload == payload
    assert persisted_log.timestamp is not None
