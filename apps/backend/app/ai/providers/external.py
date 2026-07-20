from app.ai.providers.base import LLMRequest, LLMResponse


class APIProvider:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "External API provider is not implemented in the foundation phase"
        )


class LocalProvider:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("Local model provider is not implemented in the foundation phase")
