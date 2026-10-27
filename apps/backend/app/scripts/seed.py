import argparse
import asyncio
import os

from sqlalchemy import select

import app.models  # noqa: F401
from app.common.enums import UserRole
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.modules.specialties.models import Specialty
from app.modules.topics.models import Topic
from app.modules.users.models import User


async def seed(*, admin_only: bool = False) -> None:
    if admin_only:
        missing = [key for key in ("SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD") if not os.getenv(key)]
        if missing:
            raise ValueError("Missing configuration: " + ", ".join(missing))
    admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.local").lower()
    learner_email = os.getenv("SEED_LEARNER_EMAIL", "learner@example.local").lower()
    admin_password = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe123!")
    learner_password = os.getenv("SEED_LEARNER_PASSWORD", "ChangeMe123!")

    async with SessionFactory() as session:
        accounts = (
            (admin_email, admin_password, "Development Admin", UserRole.ADMIN),
            (learner_email, learner_password, "Development Learner", UserRole.LEARNER),
        )
        for email, password, name, role in accounts[:1] if admin_only else accounts:
            existing = await session.scalar(select(User).where(User.email == email))
            if (
                existing
                and admin_only
                and (existing.role != UserRole.ADMIN or not existing.is_active)
            ):
                raise ValueError(
                    "Configured admin exists but is not an active ADMIN; no changes made"
                )
            if not existing:
                session.add(
                    User(
                        email=email,
                        hashed_password=hash_password(password),
                        full_name=name,
                        role=role,
                    )
                )

        if admin_only:
            await session.commit()
            print("Admin-only development seed completed; no learner or demo taxonomy created.")
            return

        specialty = await session.scalar(
            select(Specialty).where(Specialty.name == "Demo Specialty")
        )
        if not specialty:
            specialty = Specialty(
                name="Demo Specialty", description="Neutral development-only sample"
            )
            session.add(specialty)
            await session.flush()
        existing_topics = set(
            await session.scalars(select(Topic.name).where(Topic.specialty_id == specialty.id))
        )
        for name in ("Demo Topic 1", "Demo Topic 2"):
            if name not in existing_topics:
                session.add(Topic(specialty_id=specialty.id, name=name, description=None))
        await session.commit()
    print("Development seed completed. Credentials are read from SEED_* environment variables.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed local development records")
    parser.add_argument("--admin-only", action="store_true")
    asyncio.run(seed(admin_only=parser.parse_args().admin_only))
