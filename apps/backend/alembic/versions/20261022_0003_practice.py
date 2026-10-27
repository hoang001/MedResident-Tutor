"""Persist isolated practice, immutable input snapshots and staged results."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261022_0003"
down_revision = "20261020_0002"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("student_answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("medical_evaluation", JSONB()),
        sa.Column("teaching_feedback", JSONB()),
        sa.Column("provider_metadata", JSONB(), nullable=False),
        sa.Column("stage_error", JSONB()),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_practice_user_key"),
        sa.CheckConstraint(
            "status IN ('pending','medical_running','medical_failed',"
            "'teaching_running','teaching_failed','completed')",
            name="ck_practice_status",
        ),
        sa.CheckConstraint("execution_mode IN ('mock','http')", name="ck_practice_mode"),
    )
    op.create_index("ix_practice_attempts_user_id", "practice_attempts", ["user_id"])


def downgrade():
    op.drop_index("ix_practice_attempts_user_id", table_name="practice_attempts")
    op.drop_table("practice_attempts")
