import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import AttemptStatus
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Exam(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exams"
    title: Mapped[str] = mapped_column(String(255))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    question_order: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)


class ExamAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "exam_attempts"
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus), default=AttemptStatus.IN_PROGRESS
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_score: Mapped[float | None] = mapped_column(Float)


class UserAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_answers"
    __table_args__ = (
        Index("ux_attempt_question_answer", "attempt_id", "question_id", unique=True),
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="CASCADE")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("question_options.id", ondelete="SET NULL")
    )
    text_answer: Mapped[str | None] = mapped_column(Text)
    awarded_score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(Text)
    grading_details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
