from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class LLMRequest:
    prompt: str
    context: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str


@dataclass(slots=True)
class RetrievedDocument:
    content: str
    document_id: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...


class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class RerankerProvider(Protocol):
    async def rerank(
        self, query: str, documents: list[RetrievedDocument]
    ) -> list[RetrievedDocument]: ...
