import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.import_models import ImportIdentityMixin
from app.common.models import UUIDPrimaryKeyMixin
from app.core.database import Base


class SourceUnit(ImportIdentityMixin, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "source_units"
    __table_args__ = (
        CheckConstraint("length(trim(external_id)) > 0", name="ck_source_units_external_id"),
        CheckConstraint("length(trim(content)) > 0", name="ck_source_units_content"),
        CheckConstraint(
            "pdf_page_start >= 1 AND pdf_page_end >= pdf_page_start",
            name="ck_source_units_pdf_pages",
        ),
        CheckConstraint(
            "(printed_page_start IS NULL AND printed_page_end IS NULL) OR "
            "(printed_page_start IS NOT NULL AND printed_page_end IS NOT NULL AND "
            "printed_page_start >= 1 AND printed_page_end >= printed_page_start)",
            name="ck_source_units_printed_pages",
        ),
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    chapter: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    subsection: Mapped[str | None] = mapped_column(Text)
    pdf_page_start: Mapped[int] = mapped_column(Integer)
    pdf_page_end: Mapped[int] = mapped_column(Integer)
    printed_page_start: Mapped[int | None] = mapped_column(Integer)
    printed_page_end: Mapped[int | None] = mapped_column(Integer)
