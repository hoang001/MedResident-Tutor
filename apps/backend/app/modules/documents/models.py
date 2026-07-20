from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import DocumentProcessingStatus, RelationType
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_status_created", "processing_status", "created_at"),)

    specialty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("specialties.id", ondelete="SET NULL"), index=True
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(1000), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    version: Mapped[str] = mapped_column(String(50), default="1")
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        Enum(DocumentProcessingStatus), default=DocumentProcessingStatus.UPLOADED
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    creator: Mapped[User] = relationship(back_populates="documents")
    sections: Mapped[list[DocumentSection]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentSection(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_sections"
    __table_args__ = (Index("ix_document_sections_document_order", "document_id", "section_index"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(500))
    chapter: Mapped[str | None] = mapped_column(String(255))
    section: Mapped[str | None] = mapped_column(String(255))
    page_start: Mapped[int | None]
    page_end: Mapped[int | None]
    content: Mapped[str] = mapped_column(Text)
    section_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped[Document] = relationship(back_populates="sections")


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunks_document_order", "document_id", "chunk_index"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_sections.id", ondelete="SET NULL")
    )
    chunk_index: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped[Document] = relationship(back_populates="chunks")


class Concept(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "concepts"
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)


class ConceptRelation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "concept_relations"
    __table_args__ = (
        Index(
            "ux_concept_relation",
            "source_concept_id",
            "target_concept_id",
            "relation_type",
            unique=True,
        ),
    )
    source_concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE")
    )
    target_concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE")
    )
    relation_type: Mapped[RelationType] = mapped_column(Enum(RelationType))
    weight: Mapped[float | None] = mapped_column(Float)
    relation_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)


class DocumentConcept(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_concepts"
    __table_args__ = (
        Index("ux_document_concept", "document_id", "section_id", "concept_id", unique=True),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_sections.id", ondelete="CASCADE")
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("concepts.id", ondelete="CASCADE"))
    relevance_score: Mapped[float | None] = mapped_column(Float)


if TYPE_CHECKING:
    from app.modules.users.models import User
