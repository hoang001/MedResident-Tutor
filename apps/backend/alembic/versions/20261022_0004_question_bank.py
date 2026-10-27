"""Application availability is separate from expert review; optimistic edit version."""

import sqlalchemy as sa

from alembic import op

revision = "20261022_0004"
down_revision = "20261022_0003"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "questions",
        sa.Column("is_available", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "questions",
        sa.Column("bank_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint("ck_question_bank_version", "questions", "bank_version >= 1")
    # Preserve the previous practice listing behavior for existing mapped questions.
    # This backfill changes application availability only, never review metadata.
    op.execute("""UPDATE questions q SET is_available = true
        WHERE q.external_id IS NOT NULL
        AND EXISTS (SELECT 1 FROM rubrics r JOIN rubric_criteria c ON c.rubric_id=r.id
            WHERE r.question_id=q.id)
        AND NOT EXISTS (SELECT 1 FROM rubrics r JOIN rubric_criteria c ON c.rubric_id=r.id
            WHERE r.question_id=q.id AND NOT EXISTS
            (SELECT 1 FROM rubric_criterion_source_units m WHERE m.criterion_id=c.id))""")


def downgrade():
    op.drop_constraint("ck_question_bank_version", "questions", type_="check")
    op.drop_column("questions", "bank_version")
    op.drop_column("questions", "is_available")
