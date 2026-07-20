import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.specialties.models import Specialty
from app.modules.topics.models import Topic
from app.modules.topics.repository import TopicRepository
from app.modules.topics.schemas import TopicCreate


class TopicService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TopicRepository(session)

    async def list(self, limit: int, offset: int) -> list[Topic]:
        return await self.repository.list(limit, offset)

    async def get(self, topic_id: uuid.UUID) -> Topic:
        topic = await self.repository.get(topic_id)
        if not topic:
            raise NotFoundError("TOPIC_NOT_FOUND", "Topic not found")
        return topic

    async def create(self, data: TopicCreate) -> Topic:
        if not await self.session.get(Specialty, data.specialty_id):
            raise NotFoundError("SPECIALTY_NOT_FOUND", "Specialty not found")
        if data.parent_topic_id and not await self.repository.get(data.parent_topic_id):
            raise NotFoundError("PARENT_TOPIC_NOT_FOUND", "Parent topic not found")
        return await self.repository.add(Topic(**data.model_dump()))
