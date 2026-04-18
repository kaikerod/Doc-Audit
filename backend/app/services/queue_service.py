from __future__ import annotations

import socket
from urllib.parse import urlparse
from uuid import UUID

from ..config import settings
from ..workers.tasks import process_upload_document


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


def enqueue_upload_processing(upload_id: UUID, *, position: int = 0) -> str:
    countdown = max(position, 0) * max(settings.upload_enqueue_spacing_seconds, 0)
    async_result = process_upload_document.apply_async(args=[str(upload_id)], countdown=countdown)
    return str(async_result.id)
