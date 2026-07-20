import uuid

from app.ai.providers.base import RetrievedDocument


class MockRetriever:
    async def retrieve(
        self, query: str, topic_id: uuid.UUID | None, top_k: int
    ) -> list[RetrievedDocument]:
        return []
