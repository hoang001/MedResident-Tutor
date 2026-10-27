"""Practice records are deliberately independent of exams and mastery."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class PracticeAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "practice_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_user_key"),
        CheckConstraint(
            "status IN ('pending','medical_running','medical_failed',"
            "'teaching_running','teaching_failed','completed')",
            name="ck_practice_status",
        ),
        CheckConstraint("execution_mode IN ('mock','http')", name="ck_practice_mode"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    input_hash: Mapped[str] = mapped_column(String(64))
    student_answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    execution_mode: Mapped[str] = mapped_column(String(16))
    snapshot: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    medical_evaluation: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    teaching_feedback: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    provider_metadata: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    stage_error: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    claim_token: Mapped[uuid.UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
