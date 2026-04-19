from __future__ import annotations

from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from ..config import settings


def _upload_queue_payload_key(upload_id: str | UUID) -> str:
    return f"docaudit:uploads:payload:{upload_id}"


def _build_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=1.5,
        socket_timeout=1.5,
    )


def stage_upload_content(upload_id: str | UUID, content: bytes) -> None:
    try:
        _build_redis_client().setex(
            _upload_queue_payload_key(upload_id),
            settings.upload_queue_payload_ttl_seconds,
            content,
        )
    except (OSError, RedisError) as exc:
        raise RuntimeError("Falha ao armazenar o conteudo do upload no Redis.") from exc


def get_staged_upload_content(upload_id: str | UUID) -> bytes | None:
    try:
        payload = _build_redis_client().get(_upload_queue_payload_key(upload_id))
    except (OSError, RedisError) as exc:
        raise RuntimeError("Falha ao recuperar o conteudo do upload no Redis.") from exc

    if payload is None:
        return None

    if isinstance(payload, bytes):
        return payload

    if isinstance(payload, memoryview):
        return payload.tobytes()

    return str(payload).encode("utf-8")


def delete_staged_upload_content(upload_id: str | UUID) -> None:
    try:
        _build_redis_client().delete(_upload_queue_payload_key(upload_id))
    except (OSError, RedisError):
        return
