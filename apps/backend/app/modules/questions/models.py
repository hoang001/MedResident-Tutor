import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import QuestionType
from app.common.import_models import ImportIdentityMixin
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Question(ImportIdentityMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (CheckConstraint("bank_version >= 1", name="ck_question_bank_version"),)
    is_available: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    bank_version: Mapped[int] = mapped_column(Integer, server_default=text("1"), default=1)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
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


class Rubric(ImportIdentityMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubrics"
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(255))
    max_score: Mapped[float] = mapped_column(Float)


class RubricCriterion(ImportIdentityMixin, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rubric_criteria"
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    required_concepts: Mapped[list[Any] | None] = mapped_column(JSON)
    criterion_order: Mapped[int] = mapped_column(Integer)


class RubricCriterionSourceUnit(Base):
    __tablename__ = "rubric_criterion_source_units"
    __table_args__ = (
        UniqueConstraint("criterion_id", "evidence_order", name="uq_criterion_evidence_order"),
        CheckConstraint("evidence_order >= 1", name="ck_criterion_evidence_order"),
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rubric_criteria.id", ondelete="CASCADE"), primary_key=True
    )
    source_unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_units.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    evidence_order: Mapped[int] = mapped_column(Integer)
