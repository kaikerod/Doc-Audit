from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select

from ..config import settings
from ..database import DbSession, get_db
from ..models.upload import Upload
from ..schemas.upload import UploadBatchResponse, UploadListResponse, UploadRead
from ..services.audit_service import log_audit_event
from ..services.document_processing_service import (
    TxtDecodingError,
    build_failed_upload_bundle,
    build_processed_upload_bundle,
    build_pending_upload_bundle,
    cleanup_failed_uploads,
    cleanup_pending_uploads,
    cleanup_processed_uploads,
    persist_failed_uploads,
    persist_processed_uploads,
    persist_pending_uploads,
)
from ..services.queue_service import enqueue_upload_processing
from ..services.upload_queue_payload_service import delete_staged_upload_content, stage_upload_content
from ..services.upload_service import UploadNotFoundError, delete_all_uploads, delete_upload

router = APIRouter(prefix=f"{settings.api_v1_prefix}/uploads", tags=["uploads"])


def get_upload_storage_dir() -> Path:
    storage_dir = Path(settings.upload_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _validate_upload_count(file_count: int) -> None:
    if file_count > settings.upload_max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite maximo de {settings.upload_max_files} arquivos por envio.",
        )


def _validate_upload_content(content: bytes) -> None:
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


def _should_stage_upload_content_in_redis() -> bool:
    return settings.is_vercel and settings.processing_mode == "queue"


def _extract_txt_files_from_zip(content: bytes) -> list[tuple[str, bytes]]:
    _validate_upload_content(content)

    try:
        with ZipFile(BytesIO(content)) as archive:
            extracted_files: list[tuple[str, bytes]] = []

            for member in archive.infolist():
                if member.is_dir():
                    continue

                member_name = Path(member.filename.replace("\\", "/")).as_posix()
                if Path(member_name).suffix.lower() != ".txt":
                    continue

                if member.file_size <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Arquivos vazios nao sao permitidos.",
                    )

                if member.file_size > settings.upload_max_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Arquivo excede o limite de {settings.upload_max_size_bytes} bytes.",
                    )

                try:
                    member_content = archive.read(member)
                except Exception as exc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Nao foi possivel ler os arquivos .txt do .zip enviado.",
                    ) from exc

                _validate_upload_content(member_content)
                extracted_files.append((member_name, member_content))
    except BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo .zip invalido ou corrompido.",
        ) from exc

    if not extracted_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo .zip precisa conter ao menos um arquivo .txt.",
        )

    return extracted_files


def _expand_upload_file(filename: str, content: bytes) -> list[tuple[str, bytes]]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        _validate_upload_content(content)
        return [(filename, content)]

    if suffix == ".zip":
        return _extract_txt_files_from_zip(content)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Apenas arquivos .txt ou .zip sao permitidos.",
    )


def _get_upload_or_404(db: DbSession, upload_id: UUID) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload nao encontrado.",
        )
    return upload


def _persist_failed_upload_record(
    *,
    db: DbSession,
    original_name: str,
    content: bytes,
    storage_dir: Path,
    error_message: str,
    request_ip: str | None,
) -> Upload:
    failed_upload = build_failed_upload_bundle(
        original_name=original_name,
        content=content,
        storage_dir=storage_dir,
        error_message=error_message,
    )
    try:
        persist_failed_uploads(db, [failed_upload], ip=request_ip)
    except Exception:
        db.rollback()
        cleanup_failed_uploads([failed_upload])
        raise

    return failed_upload.upload


def _handle_sync_upload(
    *,
    db: DbSession,
    original_name: str,
    content: bytes,
    storage_dir: Path,
    request_ip: str | None,
) -> Upload:
    try:
        processed_upload = build_processed_upload_bundle(
            db,
            original_name=original_name,
            content=content,
            storage_dir=storage_dir,
        )
        try:
            persist_processed_uploads(db, [processed_upload], ip=request_ip)
        except Exception:
            db.rollback()
            cleanup_processed_uploads([processed_upload])
            raise

        return processed_upload.upload
    except TxtDecodingError as exc:
        db.rollback()
        return _persist_failed_upload_record(
            db=db,
            original_name=original_name,
            content=content,
            storage_dir=storage_dir,
            error_message=str(exc),
            request_ip=request_ip,
        )
    except Exception as exc:
        db.rollback()
        return _persist_failed_upload_record(
            db=db,
            original_name=original_name,
            content=content,
            storage_dir=storage_dir,
            error_message=str(exc),
            request_ip=request_ip,
        )


@router.post(
    "",
    response_model=UploadBatchResponse,
    summary="Realiza o upload de multiplos arquivos",
    description=(
        f"Recebe ate {settings.upload_max_files} arquivos .txt por envio, incluindo "
        "arquivos extraidos de pacotes .zip. Cada item e validado por extensao e "
        "tamanho antes de seguir para processamento."
    ),
)
async def create_uploads(
    request: Request,
    files: list[UploadFile] = File(...),
    db: DbSession = Depends(get_db),
    storage_dir: Path = Depends(get_upload_storage_dir),
) -> UploadBatchResponse:
    _validate_upload_count(len(files))

    validated_files: list[tuple[str, bytes]] = []
    persisted_uploads: list[Upload] = []
    request_ip = request.client.host if request.client else None

    for uploaded_file in files:
        original_name = Path(uploaded_file.filename or "").name
        content = await uploaded_file.read()

        validated_files.extend(_expand_upload_file(original_name, content))
        _validate_upload_count(len(validated_files))

    for original_name, content in validated_files:
        if settings.processing_mode == "sync":
            persisted_uploads.append(
                _handle_sync_upload(
                    db=db,
                    original_name=original_name,
                    content=content,
                    storage_dir=storage_dir,
                    request_ip=request_ip,
                )
            )
            continue

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
                if _should_stage_upload_content_in_redis():
                    stage_upload_content(pending_upload.upload.id, content)
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
                delete_staged_upload_content(pending_upload.upload.id)
                db.refresh(pending_upload.upload)

            persisted_uploads.append(pending_upload.upload)
        except TxtDecodingError as exc:
            db.rollback()
            persisted_uploads.append(
                _persist_failed_upload_record(
                    db=db,
                    original_name=original_name,
                    content=content,
                    storage_dir=storage_dir,
                    error_message=str(exc),
                    request_ip=request_ip,
                )
            )
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
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove todos os uploads",
    description="Exclui todos os registros de upload e seus arquivos fisicos. Esta acao e registrada no log de auditoria.",
)
def remove_all_uploads(
    request: Request,
    db: DbSession = Depends(get_db),
) -> Response:
    delete_all_uploads(
        db,
        ip=request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um upload",
    description="Exclui o registro do upload e o arquivo fisico associado. Esta acao e registrada no log de auditoria.",
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
