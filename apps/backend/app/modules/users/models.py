from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import UserRole
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.LEARNER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    documents: Mapped[list[Document]] = relationship(back_populates="creator")


if TYPE_CHECKING:
    from app.modules.documents.models import Document
