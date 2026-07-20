from app.ai.providers.base import LLMProvider, LLMRequest
from app.ai.rag.schemas import Citation, RAGQueryRequest, RAGQueryResponse
from app.ai.retrieval.base import Retriever


class RAGService:
    def __init__(self, provider: LLMProvider, retriever: Retriever) -> None:
        self.provider = provider
        self.retriever = retriever

    async def query(self, request: RAGQueryRequest) -> RAGQueryResponse:
        documents = await self.retriever.retrieve(request.question, request.topic_id, top_k=5)
        response = await self.provider.generate(
            LLMRequest(prompt=request.question, context=[item.content for item in documents])
        )
        return RAGQueryResponse(
            answer=response.text,
            citations=[
                Citation(document_id=item.document_id, excerpt=item.content[:300], score=item.score)
                for item in documents
            ],
            grounded=False,
            warning=(
                "Development mock only: retrieval and a real LLM are not configured. "
                "Do not use this output for diagnosis or clinical decisions."
            ),
            provider=response.provider,
        )
