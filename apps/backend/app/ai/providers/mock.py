from app.ai.providers.base import LLMRequest, LLMResponse


class MockLLMProvider:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=(
                "Mock response: a real language model and grounded medical knowledge base "
                "are not configured. No medical answer has been generated."
            ),
            provider="mock",
        )


class MockEmbeddingProvider:
    """Deterministic development-only embeddings; never use for retrieval quality."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0, 0.0] for text in texts]
