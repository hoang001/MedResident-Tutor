import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.common.enums import DocumentProcessingStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    specialty_id: uuid.UUID | None
    topic_id: uuid.UUID | None
    name: str
    original_filename: str
    mime_type: str
    file_size: int
    source_name: str | None
    source_url: str | None
    version: str
    processing_status: DocumentProcessingStatus
    processing_error: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
