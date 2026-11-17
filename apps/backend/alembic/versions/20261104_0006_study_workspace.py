"""Add personal reading records, ungraded self-study, and source-review history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261104_0006"
down_revision = "20261027_0005"
branch_labels = depends_on = None


def common():
    return [
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "study_records",
        *common(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("node_id", sa.String(300), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("read_state", sa.String(16), nullable=False),
        sa.Column("bookmarked", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "node_id", name="uq_study_record_user_node"),
        sa.CheckConstraint("read_state IN ('unread','reading','read')", name="ck_study_read_state"),
        sa.CheckConstraint("version > 0", name="ck_study_record_version"),
    )
    op.create_index("ix_study_records_user_id", "study_records", ["user_id"])
    op.create_table(
        "study_sessions",
        *common(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_study_session_user_key"),
        sa.CheckConstraint("status IN ('draft','submitted')", name="ck_study_session_status"),
        sa.CheckConstraint("version > 0", name="ck_study_session_version"),
    )
    op.create_index("ix_study_sessions_user_id", "study_sessions", ["user_id"])
    op.create_table(
        "knowledge_reviews",
        *common(),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("node_id", sa.String(300), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('needs_review','source_checked','needs_correction')",
            name="ck_knowledge_review_status",
        ),
    )
    op.create_index("ix_knowledge_reviews_node_id", "knowledge_reviews", ["node_id"])


def downgrade():
    op.drop_table("knowledge_reviews")
    op.drop_table("study_sessions")
    op.drop_table("study_records")
