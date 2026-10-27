"""Direct rubric evidence and stable import identity; PostgreSQL only."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261020_0002"
down_revision = "20260714_0001"
branch_labels = None
depends_on = None

IDENTITY_TABLES = ("documents", "questions", "rubrics", "rubric_criteria")


def upgrade() -> None:
    # Deliberately no checkfirst / IF NOT EXISTS: unexpected existing objects are drift.
    for table in IDENTITY_TABLES:
        op.add_column(table, sa.Column("external_id", sa.String(255), nullable=True))
        op.add_column(table, sa.Column("import_metadata", postgresql.JSONB(), nullable=True))
        op.create_unique_constraint(f"uq_{table}_external_id", table, ["external_id"])
    op.add_column("documents", sa.Column("source_sha256", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_documents_sha256",
        "documents",
        "source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.alter_column("questions", "topic_id", existing_type=sa.Uuid(), nullable=True)
    op.create_table(
        "source_units",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("external_id", sa.String(255), nullable=False, unique=True),
        sa.Column("import_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chapter", sa.Text()),
        sa.Column("section", sa.Text()),
        sa.Column("subsection", sa.Text()),
        sa.Column("pdf_page_start", sa.Integer(), nullable=False),
        sa.Column("pdf_page_end", sa.Integer(), nullable=False),
        sa.Column("printed_page_start", sa.Integer()),
        sa.Column("printed_page_end", sa.Integer()),
        sa.CheckConstraint("length(trim(external_id)) > 0", name="ck_source_units_external_id"),
        sa.CheckConstraint("length(trim(content)) > 0", name="ck_source_units_content"),
        sa.CheckConstraint(
            "pdf_page_start >= 1 AND pdf_page_end >= pdf_page_start",
            name="ck_source_units_pdf_pages",
        ),
        sa.CheckConstraint(
            "(printed_page_start IS NULL AND printed_page_end IS NULL) OR "
            "(printed_page_start IS NOT NULL AND printed_page_end IS NOT NULL AND "
            "printed_page_start >= 1 AND printed_page_end >= printed_page_start)",
            name="ck_source_units_printed_pages",
        ),
    )
    op.create_index("ix_source_units_document_id", "source_units", ["document_id"])
    op.create_table(
        "rubric_criterion_source_units",
        sa.Column(
            "criterion_id",
            sa.Uuid(),
            sa.ForeignKey("rubric_criteria.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_unit_id",
            sa.Uuid(),
            sa.ForeignKey("source_units.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("evidence_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("criterion_id", "evidence_order", name="uq_criterion_evidence_order"),
        sa.CheckConstraint("evidence_order >= 1", name="ck_criterion_evidence_order"),
    )
    op.create_index(
        "ix_rubric_criterion_source_units_source_unit_id",
        "rubric_criterion_source_units",
        ["source_unit_id"],
    )


def downgrade() -> None:
    # Refuse to discard imported records or re-impose NOT NULL on unmapped questions.
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM source_units) OR "
            "EXISTS(SELECT 1 FROM questions WHERE topic_id IS NULL) OR "
            "EXISTS(SELECT 1 FROM documents WHERE external_id IS NOT NULL)"
        )
    ).scalar():
        raise RuntimeError("Downgrade refused: integration data exists; review/export it first")
    for table in IDENTITY_TABLES:
        if connection.execute(
            sa.text(
                f"SELECT EXISTS(SELECT 1 FROM {table} "
                "WHERE external_id IS NOT NULL OR import_metadata IS NOT NULL)"
            )
        ).scalar():
            raise RuntimeError("Downgrade refused: imported identity/metadata exists")
    op.drop_table("rubric_criterion_source_units")
    op.drop_table("source_units")
    op.alter_column("questions", "topic_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("ck_documents_sha256", "documents", type_="check")
    op.drop_column("documents", "source_sha256")
    for table in reversed(IDENTITY_TABLES):
        op.drop_constraint(f"uq_{table}_external_id", table, type_="unique")
        op.drop_column(table, "import_metadata")
        op.drop_column(table, "external_id")
