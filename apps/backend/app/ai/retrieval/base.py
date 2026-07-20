import uuid
from typing import Protocol

from app.ai.providers.base import RetrievedDocument


class Retriever(Protocol):
    async def retrieve(
        self, query: str, topic_id: uuid.UUID | None, top_k: int
    ) -> list[RetrievedDocument]: ...
