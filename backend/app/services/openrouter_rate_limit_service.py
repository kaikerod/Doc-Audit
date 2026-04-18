from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from threading import Lock
import time

from redis import Redis
from redis.exceptions import RedisError

from ..config import settings

_MEMORY_LOCK = Lock()
_MEMORY_COOLDOWNS: dict[str, float] = {}
_REDIS_CLIENT: Redis | None = None
_REDIS_BACKEND_DISABLED_UNTIL_TS = 0.0
_REDIS_DISABLE_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class OpenRouterRateLimitCooldown:
    scope: str
    wait_seconds: float
    backend: str


def build_openrouter_rate_limit_scope(*, model: str | None = None) -> str:
    return f"openrouter:{model or settings.openrouter_model}"


def _redis_cooldown_key(scope: str) -> str:
    scope_hash = sha256(scope.encode("utf-8")).hexdigest()
    return f"docaudit:openrouter:rate-limit:{scope_hash}"


def _build_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
    )


def _disable_redis_backend() -> None:
    global _REDIS_BACKEND_DISABLED_UNTIL_TS
    _REDIS_BACKEND_DISABLED_UNTIL_TS = time.time() + _REDIS_DISABLE_SECONDS


def _get_redis_client() -> Redis | None:
    global _REDIS_CLIENT

    if time.time() < _REDIS_BACKEND_DISABLED_UNTIL_TS:
        return None

    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = _build_redis_client()

    return _REDIS_CLIENT


def _round_wait_seconds(wait_seconds: float) -> float:
    return round(max(0.0, wait_seconds), 3)


def _resolve_cooldown_seconds(retry_after_seconds: float | None) -> float:
    if retry_after_seconds is not None:
        return _round_wait_seconds(retry_after_seconds)

    return _round_wait_seconds(settings.openrouter_rate_limit_cooldown_seconds)


def _get_memory_cooldown(scope: str) -> OpenRouterRateLimitCooldown | None:
    now = time.time()
    with _MEMORY_LOCK:
        cooldown_until_ts = _MEMORY_COOLDOWNS.get(scope)
        if cooldown_until_ts is None:
            return None
        if cooldown_until_ts <= now:
            _MEMORY_COOLDOWNS.pop(scope, None)
            return None
        return OpenRouterRateLimitCooldown(
            scope=scope,
            wait_seconds=_round_wait_seconds(cooldown_until_ts - now),
            backend="memory",
        )


def _record_memory_cooldown(
    scope: str,
    *,
    retry_after_seconds: float | None,
) -> OpenRouterRateLimitCooldown:
    now = time.time()
    cooldown_seconds = _resolve_cooldown_seconds(retry_after_seconds)
    with _MEMORY_LOCK:
        existing_until_ts = _MEMORY_COOLDOWNS.get(scope, 0.0)
        cooldown_until_ts = max(existing_until_ts, now + cooldown_seconds)
        _MEMORY_COOLDOWNS[scope] = cooldown_until_ts
        return OpenRouterRateLimitCooldown(
            scope=scope,
            wait_seconds=_round_wait_seconds(cooldown_until_ts - now),
            backend="memory",
        )


def _get_redis_cooldown(scope: str) -> OpenRouterRateLimitCooldown | None:
    client = _get_redis_client()
    if client is None:
        return None

    try:
        ttl_ms = client.pttl(_redis_cooldown_key(scope))
    except (OSError, RedisError):
        _disable_redis_backend()
        return None

    if ttl_ms is None or ttl_ms <= 0:
        return None

    return OpenRouterRateLimitCooldown(
        scope=scope,
        wait_seconds=_round_wait_seconds(ttl_ms / 1000),
        backend="redis",
    )


def _record_redis_cooldown(
    scope: str,
    *,
    retry_after_seconds: float | None,
) -> OpenRouterRateLimitCooldown | None:
    client = _get_redis_client()
    if client is None:
        return None

    cooldown_seconds = _resolve_cooldown_seconds(retry_after_seconds)
    ttl_ms = max(100, int(math.ceil(cooldown_seconds * 1000)))
    key = _redis_cooldown_key(scope)

    try:
        existing_ttl_ms = client.pttl(key)
        resolved_ttl_ms = max(ttl_ms, existing_ttl_ms or 0)
        client.set(key, str(time.time() + (resolved_ttl_ms / 1000)), px=resolved_ttl_ms)
    except (OSError, RedisError):
        _disable_redis_backend()
        return None

    return OpenRouterRateLimitCooldown(
        scope=scope,
        wait_seconds=_round_wait_seconds(resolved_ttl_ms / 1000),
        backend="redis",
    )


def get_openrouter_rate_limit_cooldown(scope: str) -> OpenRouterRateLimitCooldown | None:
    if not settings.openrouter_rate_limit_enabled:
        return None

    redis_cooldown = _get_redis_cooldown(scope)
    if redis_cooldown is not None:
        return redis_cooldown

    return _get_memory_cooldown(scope)


def record_openrouter_rate_limit_cooldown(
    scope: str,
    *,
    retry_after_seconds: float | None,
) -> OpenRouterRateLimitCooldown:
    if not settings.openrouter_rate_limit_enabled:
        return OpenRouterRateLimitCooldown(
            scope=scope,
            wait_seconds=_resolve_cooldown_seconds(retry_after_seconds),
            backend="disabled",
        )

    redis_cooldown = _record_redis_cooldown(scope, retry_after_seconds=retry_after_seconds)
    if redis_cooldown is not None:
        return redis_cooldown

    return _record_memory_cooldown(scope, retry_after_seconds=retry_after_seconds)


def reset_openrouter_rate_limit_state() -> None:
    global _REDIS_BACKEND_DISABLED_UNTIL_TS, _REDIS_CLIENT

    with _MEMORY_LOCK:
        _MEMORY_COOLDOWNS.clear()

    _REDIS_BACKEND_DISABLED_UNTIL_TS = 0.0
    _REDIS_CLIENT = None
