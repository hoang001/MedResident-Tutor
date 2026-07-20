import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import QuestionType
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    question_type: Mapped[QuestionType] = mapped_column(Enum(QuestionType))
    content: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class QuestionOption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "question_options"
    __table_args__ = (
        Index("ux_question_option_order", "question_id", "option_order", unique=True),
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    option_order: Mapped[int] = mapped_column(Integer)


class Rubric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubrics"
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(255))
    max_score: Mapped[float] = mapped_column(Float)


class RubricCriterion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rubric_criteria"
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    required_concepts: Mapped[list[Any] | None] = mapped_column(JSON)
    criterion_order: Mapped[int] = mapped_column(Integer)
