from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from backend.app.services.queue_service import enqueue_upload_processing


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
