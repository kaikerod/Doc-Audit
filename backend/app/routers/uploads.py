from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select

from ..config import settings
from ..database import DbSession, get_db
from ..models.upload import Upload
from ..schemas.upload import UploadBatchResponse, UploadListResponse, UploadRead
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
    files: list[UploadFile] = File(...),
    db: DbSession = Depends(get_db),
    storage_dir: Path = Depends(get_upload_storage_dir),
) -> UploadBatchResponse:
    _validate_upload_count(files)

    created_uploads: list[Upload] = []

    for uploaded_file in files:
        original_name = Path(uploaded_file.filename or "").name
        content = await uploaded_file.read()

        _validate_upload_file(original_name, content)

        stored_name = f"{uuid4()}.txt"
        file_path = storage_dir / stored_name
        file_path.write_bytes(content)

        upload = Upload(
            nome_arquivo=original_name,
            caminho_arquivo=str(file_path.resolve()),
            hash_sha256=hashlib.sha256(content).hexdigest(),
            tamanho_bytes=len(content),
            status="pendente",
        )
        db.add(upload)
        created_uploads.append(upload)

    db.commit()

    for upload in created_uploads:
        db.refresh(upload)

    return UploadBatchResponse(items=created_uploads)


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
