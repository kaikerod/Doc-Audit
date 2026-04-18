from __future__ import annotations

from collections import deque
import json
import logging
from threading import Lock
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from .config import settings

_MEMORY_LOCK = Lock()
_MEMORY_EVENTS: deque[str] = deque()
_REDIS_CLIENT: Redis | None = None
_REDIS_BACKEND_DISABLED_UNTIL_TS = 0.0
_REDIS_DISABLE_SECONDS = 30.0


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None

    if normalized_value.endswith("Z"):
        normalized_value = normalized_value[:-1] + "+00:00"

    try:
        parsed_value = datetime.fromisoformat(normalized_value)
    except ValueError:
        return None

    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=timezone.utc)

    return parsed_value


def elapsed_ms(start_time: float, end_time: float | None = None) -> float:
    resolved_end = perf_counter() if end_time is None else end_time
    return round((resolved_end - start_time) * 1000, 3)


def timestamp_diff_ms(started_at: str | None, finished_at: str | None = None) -> float | None:
    start = parse_iso_timestamp(started_at)
    if start is None:
        return None

    end = parse_iso_timestamp(finished_at) if finished_at else None
    resolved_end = end or datetime.now(timezone.utc)
    return round((resolved_end - start).total_seconds() * 1000, 3)


def log_observability_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {
        "event": event,
        "timestamp": utcnow_iso(),
    }
    payload.update({key: value for key, value in fields.items() if value is not None})
    serialized_payload = json.dumps(payload, ensure_ascii=True, default=str, sort_keys=True)
    logger.log(level, serialized_payload)
    _record_observability_event(serialized_payload)


def _observability_event_key() -> str:
    return "docaudit:observability:events"


def _build_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
    )


def _disable_redis_backend() -> None:
    global _REDIS_BACKEND_DISABLED_UNTIL_TS
    _REDIS_BACKEND_DISABLED_UNTIL_TS = datetime.now(timezone.utc).timestamp() + _REDIS_DISABLE_SECONDS


def _get_redis_client() -> Redis | None:
    global _REDIS_CLIENT

    if datetime.now(timezone.utc).timestamp() < _REDIS_BACKEND_DISABLED_UNTIL_TS:
        return None

    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = _build_redis_client()

    return _REDIS_CLIENT


def _record_memory_event(serialized_payload: str) -> None:
    with _MEMORY_LOCK:
        _MEMORY_EVENTS.append(serialized_payload)
        retention = max(1, settings.observability_event_retention)
        while len(_MEMORY_EVENTS) > retention:
            _MEMORY_EVENTS.popleft()


def _record_redis_event(serialized_payload: str) -> None:
    client = _get_redis_client()
    if client is None:
        return

    try:
        client.lpush(_observability_event_key(), serialized_payload)
        client.ltrim(
            _observability_event_key(),
            0,
            max(0, settings.observability_event_retention - 1),
        )
    except (OSError, RedisError):
        _disable_redis_backend()


def _record_observability_event(serialized_payload: str) -> None:
    _record_memory_event(serialized_payload)
    _record_redis_event(serialized_payload)


def _deserialize_observability_event(serialized_payload: str) -> dict[str, Any] | None:
    try:
        event = json.loads(serialized_payload)
    except ValueError:
        return None

    return event if isinstance(event, dict) else None


def get_recent_observability_events(limit: int = 100) -> list[dict[str, Any]]:
    resolved_limit = max(1, limit)
    client = _get_redis_client()
    if client is not None:
        try:
            serialized_events = client.lrange(_observability_event_key(), 0, resolved_limit - 1)
        except (OSError, RedisError):
            _disable_redis_backend()
        else:
            return [
                event
                for serialized_event in serialized_events
                if (event := _deserialize_observability_event(serialized_event)) is not None
            ]

    with _MEMORY_LOCK:
        serialized_events = list(reversed(_MEMORY_EVENTS))[:resolved_limit]

    return [
        event
        for serialized_event in serialized_events
        if (event := _deserialize_observability_event(serialized_event)) is not None
    ]


def reset_observability_state() -> None:
    global _REDIS_BACKEND_DISABLED_UNTIL_TS, _REDIS_CLIENT

    with _MEMORY_LOCK:
        _MEMORY_EVENTS.clear()

    previous_client = _REDIS_CLIENT
    _REDIS_BACKEND_DISABLED_UNTIL_TS = 0.0
    _REDIS_CLIENT = None

    if previous_client is not None:
        try:
            previous_client.delete(_observability_event_key())
        except (OSError, RedisError):
            pass
