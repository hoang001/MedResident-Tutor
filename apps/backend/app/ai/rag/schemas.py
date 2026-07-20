import uuid

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    topic_id: uuid.UUID | None = None


class Citation(BaseModel):
    document_id: str | None = None
    excerpt: str
    score: float | None = None


class RAGQueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    grounded: bool
    warning: str | None
    provider: str
