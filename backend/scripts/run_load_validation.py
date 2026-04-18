from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

from backend.app.observability import utcnow_iso

API_PREFIX = "/api/v1"


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _build_document_payload(global_index: int) -> bytes:
    issued_day = (global_index % 27) + 1
    paid_day = min(issued_day + 1, 28)
    return (
        "NOTA FISCAL ELETRONICA\n"
        f"Numero da NF: NF-LOAD-{global_index:04d}\n"
        f"CNPJ Emitente: 11.222.333/0001-{(global_index % 89) + 10:02d}\n"
        "CNPJ Destinatario: 45.723.174/0001-10\n"
        f"Data de emissao: 2026-04-{issued_day:02d}\n"
        f"Data de pagamento: 2026-04-{paid_day:02d}\n"
        f"Valor total: {1500 + global_index * 3:.2f}\n"
        "Aprovador: Maria Silva\n"
        f"Descricao: Servico de auditoria lote {global_index}\n"
    ).encode("utf-8")


def _build_upload_files(batch_index: int, batch_size: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    base_index = (batch_index - 1) * batch_size
    for item_offset in range(batch_size):
        global_index = base_index + item_offset + 1
        files.append(
            (
                "files",
                (
                    f"load-b{batch_index:02d}-d{global_index:04d}.txt",
                    _build_document_payload(global_index),
                    "text/plain",
                ),
            )
        )
    return files


def _submit_batch(
    client: httpx.Client,
    *,
    base_url: str,
    batch_index: int,
    batch_size: int,
) -> dict[str, Any]:
    response = client.post(
        f"{base_url}{API_PREFIX}/uploads",
        files=_build_upload_files(batch_index, batch_size),
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "batch_index": batch_index,
        "submitted_at": utcnow_iso(),
        "items": payload.get("items", []),
    }


def _fetch_upload_items(
    client: httpx.Client,
    *,
    base_url: str,
    limit: int,
) -> list[dict[str, Any]]:
    response = client.get(
        f"{base_url}{API_PREFIX}/uploads",
        params={"limit": limit, "offset": 0},
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("items", []))


def _fetch_load_snapshot(
    client: httpx.Client,
    *,
    base_url: str,
    since: str,
    include_events: bool,
    event_limit: int,
) -> dict[str, Any]:
    response = client.get(
        f"{base_url}{API_PREFIX}/observability/load-validation",
        params={
            "since": since,
            "include_events": str(include_events).lower(),
            "event_limit": event_limit,
        },
    )
    response.raise_for_status()
    return response.json()


def _collect_statuses_for_uploads(
    items: list[dict[str, Any]],
    *,
    upload_ids: set[str],
) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item
        for item in items
        if str(item.get("id")) in upload_ids
    }


def _count_statuses(statuses: dict[str, dict[str, Any]]) -> dict[str, int]:
    summary = {"pendente": 0, "processando": 0, "concluido": 0, "erro": 0}
    for item in statuses.values():
        status = str(item.get("status", "")).strip().lower()
        if status in summary:
            summary[status] += 1
    return summary


def _extract_queue_total_depth(snapshot: dict[str, Any]) -> int:
    queue_payload = snapshot.get("queue")
    if isinstance(queue_payload, dict):
        total_depth = queue_payload.get("total_depth")
        if isinstance(total_depth, int):
            return total_depth
    return 0


def _extract_active_tasks(snapshot: dict[str, Any]) -> int:
    workers_payload = snapshot.get("workers")
    if not isinstance(workers_payload, dict):
        return 0

    totals_payload = workers_payload.get("totals")
    if not isinstance(totals_payload, dict):
        return 0

    active_tasks = totals_payload.get("active_tasks")
    return active_tasks if isinstance(active_tasks, int) else 0


def _build_report(
    *,
    base_url: str,
    started_at: str,
    finished_at: str,
    batches: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    timed_out: bool,
) -> dict[str, Any]:
    status_counts = _count_statuses(statuses)
    final_snapshot = snapshots[-1] if snapshots else {}
    final_metrics = final_snapshot.get("metrics", {}) if isinstance(final_snapshot, dict) else {}
    final_hint = final_metrics.get("bottleneck_hint", {}) if isinstance(final_metrics, dict) else {}
    submitted_uploads = sum(len(batch.get("items", [])) for batch in batches)

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "base_url": base_url,
        "timed_out": timed_out,
        "batches": batches,
        "summary": {
            "submitted_uploads": submitted_uploads,
            "status_counts": status_counts,
            "peak_queue_depth": max((_extract_queue_total_depth(snapshot) for snapshot in snapshots), default=0),
            "peak_active_tasks": max((_extract_active_tasks(snapshot) for snapshot in snapshots), default=0),
            "final_bottleneck_hint": {
                "label": final_hint.get("label", "insufficient_data"),
                "basis": final_hint.get("basis", "Sem inferencia final disponivel."),
            },
        },
        "uploads": list(statuses.values()),
        "snapshots": snapshots,
    }


def run_load_validation(
    *,
    base_url: str,
    batches: int,
    batch_size: int,
    pause_between_batches_seconds: float,
    poll_interval_seconds: float,
    timeout_seconds: float,
    event_limit: int,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    normalized_base_url = _normalize_base_url(base_url)
    started_at = utcnow_iso()
    submitted_batches: list[dict[str, Any]] = []
    tracked_upload_ids: set[str] = set()
    snapshots: list[dict[str, Any]] = []
    timed_out = False

    with httpx.Client(timeout=request_timeout_seconds) as client:
        for batch_index in range(1, batches + 1):
            batch_result = _submit_batch(
                client,
                base_url=normalized_base_url,
                batch_index=batch_index,
                batch_size=batch_size,
            )
            submitted_batches.append(batch_result)
            tracked_upload_ids.update(str(item["id"]) for item in batch_result["items"] if item.get("id"))
            snapshots.append(
                _fetch_load_snapshot(
                    client,
                    base_url=normalized_base_url,
                    since=started_at,
                    include_events=False,
                    event_limit=event_limit,
                )
            )

            if batch_index < batches and pause_between_batches_seconds > 0:
                time.sleep(pause_between_batches_seconds)

        deadline = time.monotonic() + timeout_seconds
        statuses: dict[str, dict[str, Any]] = {}
        while True:
            listed_uploads = _fetch_upload_items(
                client,
                base_url=normalized_base_url,
                limit=max(100, len(tracked_upload_ids) * 3),
            )
            statuses = _collect_statuses_for_uploads(listed_uploads, upload_ids=tracked_upload_ids)
            snapshots.append(
                _fetch_load_snapshot(
                    client,
                    base_url=normalized_base_url,
                    since=started_at,
                    include_events=False,
                    event_limit=event_limit,
                )
            )

            if statuses and all(
                str(item.get("status", "")).strip().lower() in {"concluido", "erro"}
                for item in statuses.values()
            ):
                break

            if time.monotonic() >= deadline:
                timed_out = True
                break

            time.sleep(poll_interval_seconds)

        snapshots.append(
            _fetch_load_snapshot(
                client,
                base_url=normalized_base_url,
                since=started_at,
                include_events=True,
                event_limit=event_limit,
            )
        )

    finished_at = utcnow_iso()
    return _build_report(
        base_url=normalized_base_url,
        started_at=started_at,
        finished_at=finished_at,
        batches=submitted_batches,
        snapshots=snapshots,
        statuses=statuses,
        timed_out=timed_out,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dispara lotes controlados de upload e coleta snapshots para validacao de carga."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--batches", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--pause-between-batches-seconds", type=float, default=0.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--event-limit", type=int, default=1000)
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_load_validation(
        base_url=args.base_url,
        batches=max(1, args.batches),
        batch_size=max(1, min(250, args.batch_size)),
        pause_between_batches_seconds=max(0.0, args.pause_between_batches_seconds),
        poll_interval_seconds=max(0.5, args.poll_interval_seconds),
        timeout_seconds=max(5.0, args.timeout_seconds),
        event_limit=max(10, args.event_limit),
        request_timeout_seconds=max(1.0, args.request_timeout_seconds),
    )
    serialized_report = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized_report + "\n", encoding="utf-8")
        print(f"Relatorio salvo em {args.output}")
    else:
        print(serialized_report)

    return 1 if report["timed_out"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
