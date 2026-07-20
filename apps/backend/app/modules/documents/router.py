import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.modules.auth.dependencies import AdminUser, CurrentUser
from app.modules.documents.schemas import DocumentResponse
from app.modules.documents.service import DocumentService
from app.storage.local import LocalFileStorage

router = APIRouter(prefix="/documents", tags=["documents"])


def get_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentService:
    return DocumentService(session, LocalFileStorage(settings.file_storage_path), settings)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    _user: CurrentUser,
    service: Annotated[DocumentService, Depends(get_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list(limit, offset)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    admin: AdminUser,
    service: Annotated[DocumentService, Depends(get_service)],
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    specialty_id: Annotated[uuid.UUID | None, Form()] = None,
    topic_id: Annotated[uuid.UUID | None, Form()] = None,
):
    return await service.upload(file, admin.id, name, specialty_id, topic_id)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    _user: CurrentUser,
    service: Annotated[DocumentService, Depends(get_service)],
):
    return await service.get(document_id)
