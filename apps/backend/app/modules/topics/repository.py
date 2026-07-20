import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.topics.models import Topic


class TopicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, limit: int, offset: int) -> list[Topic]:
        result = await self.session.scalars(
            select(Topic).order_by(Topic.name).limit(limit).offset(offset)
        )
        return list(result)

    async def get(self, topic_id: uuid.UUID) -> Topic | None:
        return await self.session.get(Topic, topic_id)

    async def add(self, topic: Topic) -> Topic:
        self.session.add(topic)
        await self.session.commit()
        await self.session.refresh(topic)
        return topic
