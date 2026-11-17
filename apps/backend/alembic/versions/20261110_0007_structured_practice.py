"""Add deterministic practice results without rewriting old attempts."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261110_0007"
down_revision = "20261104_0006"
branch_labels = depends_on = None


def upgrade():
    op.add_column("practice_attempts", sa.Column("structured_result", JSONB(), nullable=True))
    op.drop_constraint("ck_practice_mode", "practice_attempts", type_="check")
    op.create_check_constraint(
        "ck_practice_mode", "practice_attempts", "execution_mode IN ('mock','http','structured')"
    )


def downgrade():
    # Deliberately refuse to erase structured results/attempts.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM practice_attempts "
        "WHERE execution_mode='structured') THEN "
        "RAISE EXCEPTION 'Preserve structured attempts before downgrade'; "
        "END IF; END $$"
    )
    op.drop_constraint("ck_practice_mode", "practice_attempts", type_="check")
    op.create_check_constraint(
        "ck_practice_mode", "practice_attempts", "execution_mode IN ('mock','http')"
    )
    op.drop_column("practice_attempts", "structured_result")
