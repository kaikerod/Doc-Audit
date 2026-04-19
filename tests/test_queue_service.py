from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from backend.app.config import settings
from backend.app.services.queue_service import enqueue_upload_processing
from backend.app.services.queue_service import build_queue_health_check


def test_enqueue_upload_processing_adds_observability_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    upload_id = uuid4()
    async_result = Mock(id="task-123")
    caplog.set_level("INFO", logger="backend.app.services.queue_service")

    with patch(
        "backend.app.services.queue_service.process_upload_document.apply_async",
        return_value=async_result,
    ) as apply_async:
        task_id = enqueue_upload_processing(upload_id)

    assert task_id == "task-123"
    assert apply_async.call_args.kwargs["countdown"] == 0
    assert apply_async.call_args.kwargs["kwargs"]["countdown_seconds"] == 0
    assert apply_async.call_args.kwargs["kwargs"]["queued_at"]
    assert any('"event": "upload_processing_enqueued"' in record.message for record in caplog.records)


def test_build_queue_health_check_is_not_required_in_sync_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "processing_mode", "sync")

    assert build_queue_health_check() == (
        "disabled",
        True,
        "Processamento sincrono habilitado. Redis e worker nao sao necessarios neste ambiente.",
    )
