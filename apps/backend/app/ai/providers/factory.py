from app.ai.providers.base import EmbeddingProvider, LLMProvider
from app.ai.providers.mock import MockEmbeddingProvider, MockLLMProvider
from app.core.config import Settings
from app.core.exceptions import AppError


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    raise AppError(
        "AI_PROVIDER_NOT_CONFIGURED",
        f"LLM provider '{settings.llm_provider}' is not available",
        503,
    )


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider()
    raise AppError(
        "EMBEDDING_PROVIDER_NOT_CONFIGURED",
        f"Embedding provider '{settings.embedding_provider}' is not available",
        503,
    )
