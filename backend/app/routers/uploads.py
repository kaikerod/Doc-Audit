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
    ProcessedUploadBundle,
    TxtDecodingError,
    build_processed_upload_bundle,
    cleanup_processed_uploads,
    persist_processed_uploads,
)
from ..services.ia_service import (
    IAServiceError,
    OpenRouterConfigurationError,
    OpenRouterTimeoutError,
)
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

    prepared_uploads: list[ProcessedUploadBundle] = []
    validated_files: list[tuple[str, bytes]] = []
    pending_invoice_keys: set[tuple[str, str]] = set()

    for uploaded_file in files:
        original_name = Path(uploaded_file.filename or "").name
        content = await uploaded_file.read()

        _validate_upload_file(original_name, content)
        validated_files.append((original_name, content))

    try:
        for original_name, content in validated_files:
            prepared_upload = build_processed_upload_bundle(
                db,
                original_name=original_name,
                content=content,
                storage_dir=storage_dir,
                extra_existing_invoice_keys=pending_invoice_keys,
            )
            prepared_uploads.append(prepared_upload)

            if prepared_upload.documento.numero_nf and prepared_upload.documento.cnpj_emitente:
                pending_invoice_keys.add(
                    (
                        prepared_upload.documento.numero_nf,
                        prepared_upload.documento.cnpj_emitente,
                    )
                )

        persist_processed_uploads(
            db,
            prepared_uploads,
            ip=request.client.host if request.client else None,
        )
    except TxtDecodingError as exc:
        db.rollback()
        cleanup_processed_uploads(prepared_uploads)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OpenRouterConfigurationError as exc:
        db.rollback()
        cleanup_processed_uploads(prepared_uploads)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OpenRouterTimeoutError as exc:
        db.rollback()
        cleanup_processed_uploads(prepared_uploads)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except IAServiceError as exc:
        db.rollback()
        cleanup_processed_uploads(prepared_uploads)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        cleanup_processed_uploads(prepared_uploads)
        raise

    return UploadBatchResponse(items=[processed_upload.upload for processed_upload in prepared_uploads])


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
