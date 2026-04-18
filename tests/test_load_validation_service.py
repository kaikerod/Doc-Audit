from __future__ import annotations

import logging

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.observability import log_observability_event
from backend.app.schemas.observability import (
    LoadValidationMetrics,
    LoadValidationQueueSnapshot,
    LoadValidationSnapshot,
    LoadValidationTimingSummary,
    LoadValidationWorkersSnapshot,
    LoadValidationWorkerTotals,
)
from backend.app.services.load_validation_service import build_load_validation_snapshot


class _FakeRedisClient:
    def __init__(self, queue_depths: dict[str, int]) -> None:
        self.queue_depths = queue_depths

    def llen(self, queue_name: str) -> int:
        return self.queue_depths.get(queue_name, 0)


class _FakeInspector:
    def active(self) -> dict[str, list[dict[str, str]]]:
        return {"worker-1@example": [{"id": "task-1"}]}

    def reserved(self) -> dict[str, list[dict[str, str]]]:
        return {"worker-1@example": [{"id": "task-2"}]}

    def scheduled(self) -> dict[str, list[dict[str, str]]]:
        return {"worker-1@example": []}

    def stats(self) -> dict[str, dict[str, dict[str, int]]]:
        return {"worker-1@example": {"pool": {"max-concurrency": 2}}}


def test_build_load_validation_snapshot_aggregates_queue_worker_and_event_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = logging.getLogger("tests.load_validation")
    monkeypatch.setattr(
        "backend.app.services.load_validation_service._build_redis_client",
        lambda: _FakeRedisClient({"celery": 2}),
    )
    monkeypatch.setattr(
        "backend.app.services.load_validation_service.celery_app.control.inspect",
        lambda timeout: _FakeInspector(),
    )

    log_observability_event(logger, "upload_processing_started", queue_wait_ms=900.0, upload_id="upload-1")
    log_observability_event(
        logger,
        "openrouter_request_completed",
        total_latency_ms=250.0,
        upload_id="upload-1",
    )
    log_observability_event(
        logger,
        "upload_processing_completed",
        total_latency_ms=1200.0,
        upload_id="upload-1",
    )

    snapshot = build_load_validation_snapshot(include_events=True, event_limit=50)

    assert snapshot.queue.status == "ok"
    assert snapshot.queue.total_depth == 2
    assert snapshot.workers.status == "ok"
    assert snapshot.workers.totals == LoadValidationWorkerTotals(
        online_workers=1,
        active_tasks=1,
        reserved_tasks=1,
        scheduled_tasks=0,
    )
    assert snapshot.metrics.queue_wait_ms == LoadValidationTimingSummary(
        count=1,
        avg_ms=900.0,
        min_ms=900.0,
        p50_ms=900.0,
        p95_ms=900.0,
        max_ms=900.0,
    )
    assert snapshot.metrics.upstream_latency_ms.p95_ms == 250.0
    assert snapshot.metrics.task_latency_ms.p95_ms == 1200.0
    assert snapshot.metrics.bottleneck_hint.label == "queue"
    assert len(snapshot.recent_events) == 3


def test_load_validation_endpoint_returns_snapshot_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_snapshot = LoadValidationSnapshot(
        captured_at="2026-04-18T12:00:00+00:00",
        since="2026-04-18T11:59:00+00:00",
        queue=LoadValidationQueueSnapshot(status="ok", total_depth=0),
        workers=LoadValidationWorkersSnapshot(
            status="ok",
            totals=LoadValidationWorkerTotals(),
        ),
        metrics=LoadValidationMetrics(
            observed_events=1,
            queue_wait_ms=LoadValidationTimingSummary(),
        ),
        recent_events=[],
    )
    captured_args: dict[str, object] = {}

    def _fake_builder(*, since: str | None, include_events: bool, event_limit: int) -> LoadValidationSnapshot:
        captured_args["since"] = since
        captured_args["include_events"] = include_events
        captured_args["event_limit"] = event_limit
        return expected_snapshot

    monkeypatch.setattr(
        "backend.app.routers.observability.build_load_validation_snapshot",
        _fake_builder,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/observability/load-validation",
            params={
                "since": "2026-04-18T11:59:00+00:00",
                "include_events": "true",
                "event_limit": 25,
            },
        )

    assert response.status_code == 200
    assert response.json()["captured_at"] == "2026-04-18T12:00:00+00:00"
    assert captured_args == {
        "since": "2026-04-18T11:59:00+00:00",
        "include_events": True,
        "event_limit": 25,
    }


def test_load_validation_endpoint_returns_400_for_invalid_since(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.app.routers.observability.build_load_validation_snapshot",
        lambda **_: (_ for _ in ()).throw(ValueError("Parametro 'since' invalido.")),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/observability/load-validation?since=ontem")

    assert response.status_code == 400
    assert response.json() == {"detail": "Parametro 'since' invalido."}
