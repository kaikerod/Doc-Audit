from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse
from uuid import UUID

from ..config import settings
from ..observability import log_observability_event, utcnow_iso
from ..workers.tasks import process_upload_document

logger = logging.getLogger(__name__)


def build_queue_health_check() -> tuple[str, bool, str | None]:
    parsed_url = urlparse(settings.redis_url)
    if not parsed_url.hostname:
        return (
            "misconfigured",
            False,
            "REDIS_URL invalida. Revise a configuracao da fila de processamento.",
        )

    port = parsed_url.port or 6379

    try:
        with socket.create_connection((parsed_url.hostname, port), timeout=1.5):
            return ("ok", True, None)
    except OSError:
        return (
            "unreachable",
            False,
            "Falha ao conectar ao Redis. Verifique a fila de processamento e o worker.",
        )


def enqueue_upload_processing(upload_id: UUID) -> str:
    countdown = 0
    queued_at = utcnow_iso()
    async_result = process_upload_document.apply_async(
        args=[str(upload_id)],
        kwargs={
            "queued_at": queued_at,
            "countdown_seconds": countdown,
        },
        countdown=countdown,
    )
    log_observability_event(
        logger,
        "upload_processing_enqueued",
        upload_id=str(upload_id),
        task_id=str(async_result.id),
        queued_at=queued_at,
        countdown_seconds=countdown,
    )
    return str(async_result.id)
