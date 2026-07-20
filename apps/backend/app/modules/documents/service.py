import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import DocumentProcessingStatus
from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.modules.documents.models import Document
from app.modules.documents.repository import DocumentRepository
from app.storage.base import FileStorage

ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/plain"},
}


class DocumentService:
    def __init__(self, session: AsyncSession, storage: FileStorage, settings: Settings) -> None:
        self.repository = DocumentRepository(session)
        self.storage = storage
        self.settings = settings

    async def list(self, limit: int, offset: int) -> list[Document]:
        return await self.repository.list(limit, offset)

    async def get(self, document_id: uuid.UUID) -> Document:
        document = await self.repository.get(document_id)
        if not document:
            raise NotFoundError("DOCUMENT_NOT_FOUND", "Document not found")
        return document

    async def upload(
        self,
        file: UploadFile,
        user_id: uuid.UUID,
        name: str | None,
        specialty_id: uuid.UUID | None,
        topic_id: uuid.UUID | None,
    ) -> Document:
        filename = Path(file.filename or "").name
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_TYPES or file.content_type not in ALLOWED_TYPES[extension]:
            raise AppError(
                "UNSUPPORTED_DOCUMENT_TYPE",
                "Only PDF, TXT, and Markdown files with matching MIME types are supported",
                415,
            )
        maximum = self.settings.max_upload_size_mb * 1024 * 1024
        content = await file.read(maximum + 1)
        if len(content) > maximum:
            raise AppError("FILE_TOO_LARGE", "Uploaded file exceeds configured size limit", 413)
        if not content:
            raise AppError("EMPTY_FILE", "Uploaded file is empty", 422)

        relative_path = f"{uuid.uuid4()}{extension}"
        await self.storage.save(relative_path, content)
        document = Document(
            name=(name or Path(filename).stem).strip(),
            original_filename=filename,
            storage_path=relative_path,
            mime_type=file.content_type,
            file_size=len(content),
            specialty_id=specialty_id,
            topic_id=topic_id,
            created_by=user_id,
            processing_status=DocumentProcessingStatus.UPLOADED,
        )
        try:
            return await self.repository.add(document)
        except Exception:
            await self.storage.delete(relative_path)
            raise
