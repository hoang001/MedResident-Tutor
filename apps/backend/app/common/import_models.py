"""Import identity; JSONB in PostgreSQL, JSON for existing lightweight API tests."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class ImportIdentityMixin:
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    import_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
