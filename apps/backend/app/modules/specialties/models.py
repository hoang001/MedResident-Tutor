from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Specialty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "specialties"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list["Topic"]] = relationship(back_populates="specialty")


if TYPE_CHECKING:
    from app.modules.topics.models import Topic
