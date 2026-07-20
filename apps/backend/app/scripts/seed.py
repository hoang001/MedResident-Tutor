import asyncio
import os

from sqlalchemy import select

from app.common.enums import UserRole
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.modules.specialties.models import Specialty
from app.modules.topics.models import Topic
from app.modules.users.models import User


async def seed() -> None:
    admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.local").lower()
    learner_email = os.getenv("SEED_LEARNER_EMAIL", "learner@example.local").lower()
    admin_password = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe123!")
    learner_password = os.getenv("SEED_LEARNER_PASSWORD", "ChangeMe123!")

    async with SessionFactory() as session:
        for email, password, name, role in (
            (admin_email, admin_password, "Development Admin", UserRole.ADMIN),
            (learner_email, learner_password, "Development Learner", UserRole.LEARNER),
        ):
            if not await session.scalar(select(User).where(User.email == email)):
                session.add(
                    User(
                        email=email,
                        hashed_password=hash_password(password),
                        full_name=name,
                        role=role,
                    )
                )

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
    asyncio.run(seed())
