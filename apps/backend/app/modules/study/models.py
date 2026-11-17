import uuid

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class StudyRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "study_records"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_study_record_user_node"),
        CheckConstraint("read_state IN ('unread','reading','read')", name="ck_study_read_state"),
        CheckConstraint("version > 0", name="ck_study_record_version"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(Text)
    read_state: Mapped[str] = mapped_column(String(16))
    bookmarked: Mapped[bool]
    note: Mapped[str] = mapped_column(Text)
    revision: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class StudySession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_study_session_user_key"),
        CheckConstraint("status IN ('draft','submitted')", name="ck_study_session_status"),
        CheckConstraint("version > 0", name="ck_study_session_version"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    questions: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    answers: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class KnowledgeReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('needs_review','source_checked','needs_correction')",
            name="ck_knowledge_review_status",
        ),
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    node_id: Mapped[str] = mapped_column(String(300), index=True)
    revision: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text)
