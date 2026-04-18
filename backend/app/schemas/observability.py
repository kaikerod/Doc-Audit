from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoadValidationTimingSummary(BaseModel):
    count: int = 0
    avg_ms: float | None = None
    min_ms: float | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None


class LoadValidationBottleneckHint(BaseModel):
    label: str = "insufficient_data"
    basis: str = "Sem eventos suficientes para inferencia."


class LoadValidationQueueDepth(BaseModel):
    name: str
    depth: int | None = None


class LoadValidationQueueSnapshot(BaseModel):
    status: str
    total_depth: int | None = None
    queues: list[LoadValidationQueueDepth] = Field(default_factory=list)
    detail: str | None = None


class LoadValidationWorkerSnapshot(BaseModel):
    hostname: str
    active_tasks: int = 0
    reserved_tasks: int = 0
    scheduled_tasks: int = 0
    pool_max_concurrency: int | None = None


class LoadValidationWorkerTotals(BaseModel):
    online_workers: int = 0
    active_tasks: int = 0
    reserved_tasks: int = 0
    scheduled_tasks: int = 0


class LoadValidationWorkersSnapshot(BaseModel):
    status: str
    totals: LoadValidationWorkerTotals = Field(default_factory=LoadValidationWorkerTotals)
    workers: list[LoadValidationWorkerSnapshot] = Field(default_factory=list)
    detail: str | None = None


class LoadValidationMetrics(BaseModel):
    observed_window_started_at: str | None = None
    observed_window_ended_at: str | None = None
    observed_events: int = 0
    event_counts: dict[str, int] = Field(default_factory=dict)
    queue_wait_ms: LoadValidationTimingSummary = Field(default_factory=LoadValidationTimingSummary)
    task_latency_ms: LoadValidationTimingSummary = Field(default_factory=LoadValidationTimingSummary)
    upstream_latency_ms: LoadValidationTimingSummary = Field(default_factory=LoadValidationTimingSummary)
    completed_uploads: int = 0
    failed_uploads: int = 0
    scheduled_retries: int = 0
    rate_limit_events: int = 0
    timeout_events: int = 0
    bottleneck_hint: LoadValidationBottleneckHint = Field(
        default_factory=LoadValidationBottleneckHint
    )


class LoadValidationSnapshot(BaseModel):
    captured_at: str
    since: str | None = None
    queue: LoadValidationQueueSnapshot
    workers: LoadValidationWorkersSnapshot
    metrics: LoadValidationMetrics
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
