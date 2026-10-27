"""Run only in the explicitly isolated browser DB, never development."""

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url

import app.models  # noqa: F401
from app.common.enums import UserRole
from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.core.security import hash_password
from app.integration.importer import import_case
from app.modules.users.models import User


async def main():
    import sys

    synthetic_bank = "--synthetic-bank" in sys.argv
    cfg = get_settings()
    assert cfg.app_env == "development"
    assert make_url(cfg.database_url).database == "medresident_test_browser"
    async with SessionFactory() as s, s.begin():
        for email, role in (
            ("fixture-admin@example.com", UserRole.ADMIN),
            ("first@example.com", UserRole.LEARNER),
            ("second@example.com", UserRole.LEARNER),
        ):
            if not await s.scalar(select(User).where(User.email == email)):
                s.add(
                    User(
                        email=email,
                        full_name="Browser fixture",
                        hashed_password=hash_password("BrowserFixtureOnly123!"),
                        role=role,
                        is_active=True,
                    )
                )
    async with SessionFactory() as s:
        admin = await s.scalar(select(User).where(User.email == "fixture-admin@example.com"))
    if synthetic_bank:
        from bank_fixtures import seed_sources

        async with SessionFactory() as s, s.begin():
            await seed_sources(s, admin.id, cfg.file_storage_path)
        await engine.dispose()
        print("Synthetic browser bank fixtures ready")
        return
    await import_case(
        engine,
        Path("/fixtures"),
        Path("data/integration/ORTHO_B21CN1_Q_0001.manifest.json"),
        admin.id,
        cfg.file_storage_path,
    )
    await engine.dispose()
    print("Isolated browser fixtures ready")


asyncio.run(main())
