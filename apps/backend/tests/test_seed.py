import uuid

import pytest
from sqlalchemy import func, select

from app.common.enums import UserRole
from app.core.security import verify_password
from app.modules.specialties.models import Specialty
from app.modules.topics.models import Topic
from app.modules.users.models import User
from app.scripts import seed as seed_module
from tests.conftest import TestSession


async def test_admin_only_is_idempotent_without_demo_records(monkeypatch):
    email = f"seed-{uuid.uuid4()}@example.invalid"
    monkeypatch.setenv("SEED_ADMIN_EMAIL", email)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "SyntheticTestPassword123!")
    monkeypatch.setattr(seed_module, "SessionFactory", TestSession)
    async with TestSession() as session:
        before = [
            await session.scalar(select(func.count()).select_from(t))
            for t in (User, Specialty, Topic)
        ]
    await seed_module.seed(admin_only=True)
    await seed_module.seed(admin_only=True)
    async with TestSession() as session:
        after = [
            await session.scalar(select(func.count()).select_from(t))
            for t in (User, Specialty, Topic)
        ]
        user = await session.scalar(select(User).where(User.email == email))
        assert user.role == UserRole.ADMIN and user.is_active
        assert verify_password("SyntheticTestPassword123!", user.hashed_password)
    assert after == [before[0] + 1, before[1], before[2]]


async def test_admin_only_requires_explicit_password(monkeypatch):
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="SEED_ADMIN_PASSWORD"):
        await seed_module.seed(admin_only=True)
