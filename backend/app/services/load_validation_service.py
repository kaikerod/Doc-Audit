from __future__ import annotations

from collections import Counter
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from ..config import settings
from ..observability import get_recent_observability_events, parse_iso_timestamp, utcnow_iso
from ..schemas.observability import (
    LoadValidationBottleneckHint,
    LoadValidationMetrics,
    LoadValidationQueueDepth,
    LoadValidationQueueSnapshot,
    LoadValidationSnapshot,
    LoadValidationTimingSummary,
    LoadValidationWorkerSnapshot,
    LoadValidationWorkersSnapshot,
    LoadValidationWorkerTotals,
)
from ..workers.tasks import celery_app

FAILED_UPLOAD_EVENTS = {
    "upload_processing_failed",
    "upload_processing_soft_time_limit_exceeded",
}
TASK_LATENCY_EVENTS = {
    "upload_processing_completed",
    "upload_processing_failed",
    "upload_processing_retry_scheduled",
    "upload_processing_soft_time_limit_exceeded",
}
UPSTREAM_LATENCY_EVENTS = {
    "openrouter_request_completed",
    "openrouter_request_failed",
}


def _build_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )


def _load_queue_snapshot() -> LoadValidationQueueSnapshot:
    try:
        client = _build_redis_client()
        queue_depths = [
            LoadValidationQueueDepth(name=queue_name, depth=int(client.llen(queue_name)))
            for queue_name in settings.celery_observed_queues
        ]
    except (OSError, RedisError):
        return LoadValidationQueueSnapshot(
            status="unreachable",
            total_depth=None,
            queues=[LoadValidationQueueDepth(name=queue_name) for queue_name in settings.celery_observed_queues],
            detail="Nao foi possivel consultar a profundidade da fila Redis.",
        )

    total_depth = sum(queue.depth or 0 for queue in queue_depths)
    return LoadValidationQueueSnapshot(
        status="ok",
        total_depth=total_depth,
        queues=queue_depths,
    )


def _normalize_pool_max_concurrency(stats_payload: dict[str, Any] | None) -> int | None:
    if not isinstance(stats_payload, dict):
        return None

    pool_payload = stats_payload.get("pool")
    if not isinstance(pool_payload, dict):
        return None

    raw_value = pool_payload.get("max-concurrency")
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return int(raw_value.strip())
    return None


def _build_worker_snapshot() -> LoadValidationWorkersSnapshot:
    try:
        inspector = celery_app.control.inspect(timeout=settings.celery_inspect_timeout_seconds)
        active_by_worker = inspector.active() or {}
        reserved_by_worker = inspector.reserved() or {}
        scheduled_by_worker = inspector.scheduled() or {}
        stats_by_worker = inspector.stats() or {}
    except Exception:
        return LoadValidationWorkersSnapshot(
            status="error",
            detail="Falha ao inspecionar o estado dos workers Celery.",
        )

    worker_names = sorted(
        set(active_by_worker) | set(reserved_by_worker) | set(scheduled_by_worker) | set(stats_by_worker)
    )
    if not worker_names:
        return LoadValidationWorkersSnapshot(
            status="unreachable",
            detail="Nenhum worker Celery respondeu ao inspect.",
        )

    workers = [
        LoadValidationWorkerSnapshot(
            hostname=worker_name,
            active_tasks=len(active_by_worker.get(worker_name) or []),
            reserved_tasks=len(reserved_by_worker.get(worker_name) or []),
            scheduled_tasks=len(scheduled_by_worker.get(worker_name) or []),
            pool_max_concurrency=_normalize_pool_max_concurrency(stats_by_worker.get(worker_name)),
        )
        for worker_name in worker_names
    ]
    totals = LoadValidationWorkerTotals(
        online_workers=len(workers),
        active_tasks=sum(worker.active_tasks for worker in workers),
        reserved_tasks=sum(worker.reserved_tasks for worker in workers),
        scheduled_tasks=sum(worker.scheduled_tasks for worker in workers),
    )
    return LoadValidationWorkersSnapshot(
        status="ok",
        totals=totals,
        workers=workers,
    )


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None

    ordered_values = sorted(values)
    if len(ordered_values) == 1:
        return round(ordered_values[0], 3)

    rank = (len(ordered_values) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered_values) - 1)
    weight = rank - lower_index
    interpolated_value = ordered_values[lower_index] + (
        (ordered_values[upper_index] - ordered_values[lower_index]) * weight
    )
    return round(interpolated_value, 3)


def _build_timing_summary(values: list[float]) -> LoadValidationTimingSummary:
    if not values:
        return LoadValidationTimingSummary()

    resolved_values = sorted(values)
    return LoadValidationTimingSummary(
        count=len(resolved_values),
        avg_ms=round(sum(resolved_values) / len(resolved_values), 3),
        min_ms=round(resolved_values[0], 3),
        p50_ms=_percentile(resolved_values, 0.5),
        p95_ms=_percentile(resolved_values, 0.95),
        max_ms=round(resolved_values[-1], 3),
    )


def _coerce_metric_value(event: dict[str, Any], field_name: str) -> float | None:
    raw_value = event.get(field_name)
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str):
        try:
            return float(raw_value.strip())
        except ValueError:
            return None
    return None


def _filter_events_since(
    events: list[dict[str, Any]],
    *,
    since: str | None,
) -> list[dict[str, Any]]:
    if since is None:
        return events

    since_timestamp = parse_iso_timestamp(since)
    if since_timestamp is None:
        raise ValueError("Parametro 'since' invalido. Use um timestamp ISO-8601.")

    filtered_events: list[dict[str, Any]] = []
    for event in events:
        event_timestamp = parse_iso_timestamp(str(event.get("timestamp", "")).strip() or None)
        if event_timestamp is None:
            continue
        if event_timestamp >= since_timestamp:
            filtered_events.append(event)
    return filtered_events


def _build_bottleneck_hint(
    *,
    queue_wait_summary: LoadValidationTimingSummary,
    upstream_summary: LoadValidationTimingSummary,
    rate_limit_events: int,
) -> LoadValidationBottleneckHint:
    if rate_limit_events > 0:
        return LoadValidationBottleneckHint(
            label="rate_limit",
            basis=f"Foram observados {rate_limit_events} eventos de rate limit no intervalo.",
        )

    queue_reference = queue_wait_summary.p95_ms or queue_wait_summary.avg_ms
    upstream_reference = upstream_summary.p95_ms or upstream_summary.avg_ms

    if queue_reference is None and upstream_reference is None:
        return LoadValidationBottleneckHint()

    if queue_reference is not None and upstream_reference is None:
        return LoadValidationBottleneckHint(
            label="queue",
            basis=f"Apenas tempo de fila foi observado no intervalo (p95={queue_reference} ms).",
        )

    if upstream_reference is not None and queue_reference is None:
        return LoadValidationBottleneckHint(
            label="upstream",
            basis=f"Apenas latencia de upstream foi observada no intervalo (p95={upstream_reference} ms).",
        )

    assert queue_reference is not None
    assert upstream_reference is not None

    if queue_reference >= max(250.0, upstream_reference * 1.25):
        return LoadValidationBottleneckHint(
            label="queue",
            basis=(
                "Tempo de fila dominante no intervalo "
                f"(queue_p95={queue_reference} ms, upstream_p95={upstream_reference} ms)."
            ),
        )

    if upstream_reference >= max(250.0, queue_reference * 1.25):
        return LoadValidationBottleneckHint(
            label="upstream",
            basis=(
                "Latencia de upstream dominante no intervalo "
                f"(upstream_p95={upstream_reference} ms, queue_p95={queue_reference} ms)."
            ),
        )

    return LoadValidationBottleneckHint(
        label="mixed",
        basis=(
            "Tempos de fila e upstream ficaram proximos no intervalo "
            f"(queue_p95={queue_reference} ms, upstream_p95={upstream_reference} ms)."
        ),
    )


def _build_metrics_snapshot(
    *,
    events: list[dict[str, Any]],
) -> LoadValidationMetrics:
    event_counts = Counter(
        str(event_name)
        for event in events
        if (event_name := event.get("event")) is not None
    )
    queue_wait_values = [
        metric_value
        for event in events
        if event.get("event") == "upload_processing_started"
        if (metric_value := _coerce_metric_value(event, "queue_wait_ms")) is not None
    ]
    task_latency_values = [
        metric_value
        for event in events
        if event.get("event") in TASK_LATENCY_EVENTS
        if (metric_value := _coerce_metric_value(event, "total_latency_ms")) is not None
    ]
    upstream_latency_values = [
        metric_value
        for event in events
        if event.get("event") in UPSTREAM_LATENCY_EVENTS
        if (metric_value := _coerce_metric_value(event, "total_latency_ms")) is not None
    ]
    queue_wait_summary = _build_timing_summary(queue_wait_values)
    upstream_summary = _build_timing_summary(upstream_latency_values)
    rate_limit_events = (
        event_counts.get("openrouter_rate_limit_cooldown_recorded", 0)
        + event_counts.get("openrouter_request_deferred_by_rate_limit", 0)
    )
    timeout_events = (
        event_counts.get("openrouter_request_attempt_timed_out", 0)
        + event_counts.get("upload_processing_soft_time_limit_exceeded", 0)
    )
    metrics = LoadValidationMetrics(
        observed_window_started_at=events[-1]["timestamp"] if events else None,
        observed_window_ended_at=events[0]["timestamp"] if events else None,
        observed_events=len(events),
        event_counts=dict(sorted(event_counts.items())),
        queue_wait_ms=queue_wait_summary,
        task_latency_ms=_build_timing_summary(task_latency_values),
        upstream_latency_ms=upstream_summary,
        completed_uploads=event_counts.get("upload_processing_completed", 0),
        failed_uploads=sum(event_counts.get(event_name, 0) for event_name in FAILED_UPLOAD_EVENTS),
        scheduled_retries=event_counts.get("upload_processing_retry_scheduled", 0),
        rate_limit_events=rate_limit_events,
        timeout_events=timeout_events,
        bottleneck_hint=_build_bottleneck_hint(
            queue_wait_summary=queue_wait_summary,
            upstream_summary=upstream_summary,
            rate_limit_events=rate_limit_events,
        ),
    )
    return metrics


def build_load_validation_snapshot(
    *,
    since: str | None = None,
    include_events: bool = False,
    event_limit: int = 200,
) -> LoadValidationSnapshot:
    resolved_event_limit = max(10, min(event_limit, settings.observability_event_retention))
    recent_events = get_recent_observability_events(limit=resolved_event_limit)
    filtered_events = _filter_events_since(recent_events, since=since)

    return LoadValidationSnapshot(
        captured_at=utcnow_iso(),
        since=since,
        queue=_load_queue_snapshot(),
        workers=_build_worker_snapshot(),
        metrics=_build_metrics_snapshot(events=filtered_events),
        recent_events=filtered_events if include_events else [],
    )
