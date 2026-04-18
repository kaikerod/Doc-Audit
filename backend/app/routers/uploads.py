from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select

from ..config import settings
from ..database import DbSession, get_db
from ..models.upload import Upload
from ..schemas.upload import UploadBatchResponse, UploadListResponse, UploadRead
from ..services.document_processing_service import (
    TxtDecodingError,
    build_failed_upload_bundle,
    build_pending_upload_bundle,
    cleanup_failed_uploads,
    cleanup_pending_uploads,
    persist_failed_uploads,
    persist_pending_uploads,
)
from ..services.audit_service import log_audit_event
from ..services.queue_service import enqueue_upload_processing
from ..services.upload_service import UploadNotFoundError, delete_upload

router = APIRouter(prefix=f"{settings.api_v1_prefix}/uploads", tags=["uploads"])


def get_upload_storage_dir() -> Path:
    storage_dir = Path(settings.upload_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _validate_upload_count(files: list[UploadFile]) -> None:
    if len(files) > settings.upload_max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite maximo de {settings.upload_max_files} arquivos por envio.",
        )


def _validate_upload_file(filename: str, content: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix != ".txt":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos .txt sao permitidos.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivos vazios nao sao permitidos.",
        )

    if len(content) > settings.upload_max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Arquivo excede o limite de {settings.upload_max_size_bytes} bytes.",
        )


def _get_upload_or_404(db: DbSession, upload_id: UUID) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload nao encontrado.",
        )
    return upload


@router.post(
    "",
    response_model=UploadBatchResponse,
    summary="Realiza o upload de múltiplos arquivos",
    description="Recebe até 20 arquivos .txt para processamento. Cada arquivo é validado por extensão e tamanho antes de ser enfileirado.",
)
async def create_uploads(
    request: Request,
    files: list[UploadFile] = File(...),
    db: DbSession = Depends(get_db),
    storage_dir: Path = Depends(get_upload_storage_dir),
) -> UploadBatchResponse:
    _validate_upload_count(files)

    validated_files: list[tuple[str, bytes]] = []
    persisted_uploads: list[Upload] = []
    request_ip = request.client.host if request.client else None

    for uploaded_file in files:
        original_name = Path(uploaded_file.filename or "").name
        content = await uploaded_file.read()

        _validate_upload_file(original_name, content)
        validated_files.append((original_name, content))

    for original_name, content in validated_files:
        try:
            pending_upload = build_pending_upload_bundle(
                original_name=original_name,
                content=content,
                storage_dir=storage_dir,
            )
            try:
                persist_pending_uploads(db, [pending_upload])
            except Exception:
                db.rollback()
                cleanup_pending_uploads([pending_upload])
                raise

            try:
                enqueue_upload_processing(pending_upload.upload.id)
            except Exception as exc:
                db.rollback()
                pending_upload.upload.status = "erro"
                log_audit_event(
                    db,
                    evento="processamento_erro",
                    entidade_tipo="upload",
                    entidade_id=str(pending_upload.upload.id),
                    ip=request_ip,
                    payload={
                        "upload_id": str(pending_upload.upload.id),
                        "arquivo": pending_upload.upload.nome_arquivo,
                        "erro": f"Falha ao enfileirar processamento: {exc}",
                    },
                )
                db.refresh(pending_upload.upload)

            persisted_uploads.append(pending_upload.upload)
        except TxtDecodingError as exc:
            db.rollback()
            failed_upload = build_failed_upload_bundle(
                original_name=original_name,
                content=content,
                storage_dir=storage_dir,
                error_message=str(exc),
            )
            try:
                persist_failed_uploads(db, [failed_upload], ip=request_ip)
            except Exception:
                db.rollback()
                cleanup_failed_uploads([failed_upload])
                raise

            persisted_uploads.append(failed_upload.upload)
        except Exception:
            db.rollback()
            raise

    return UploadBatchResponse(items=persisted_uploads)


@router.get(
    "",
    response_model=UploadListResponse,
    summary="Lista todos os uploads",
    description="Retorna uma lista paginada de uploads ordenados do mais recente para o mais antigo.",
)
def list_uploads(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: DbSession = Depends(get_db),
) -> UploadListResponse:
    total = db.scalar(select(func.count()).select_from(Upload)) or 0
    uploads = db.scalars(
        select(Upload)
        .order_by(Upload.criado_em.desc(), Upload.nome_arquivo.asc(), Upload.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return UploadListResponse(total=total, items=[UploadRead.model_validate(upload) for upload in uploads])


@router.get(
    "/{upload_id}",
    response_model=UploadRead,
    summary="Detalha um upload",
    description="Retorna os metadados de um upload especifico.",
)
def get_upload(
    upload_id: UUID,
    db: DbSession = Depends(get_db),
) -> UploadRead:
    return UploadRead.model_validate(_get_upload_or_404(db, upload_id))


@router.delete(
    "/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um upload",
    description="Exclui o registro do upload e o arquivo físico associado. Esta ação é registrada no log de auditoria.",
)
def remove_upload(
    upload_id: UUID,
    request: Request,
    db: DbSession = Depends(get_db),
) -> Response:
    try:
        delete_upload(
            db,
            upload_id=upload_id,
            ip=request.client.host if request.client else None,
        )
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload nao encontrado.") from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
