import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TopicCreate(BaseModel):
    specialty_id: uuid.UUID
    parent_topic_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    specialty_id: uuid.UUID
    parent_topic_id: uuid.UUID | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
