from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.providers.factory import create_llm_provider
from app.ai.rag.schemas import RAGQueryRequest, RAGQueryResponse
from app.ai.rag.service import RAGService
from app.ai.retrieval.mock import MockRetriever
from app.core.config import Settings, get_settings
from app.modules.auth.dependencies import CurrentUser

router = APIRouter(prefix="/ai/rag", tags=["ai"])


def get_rag_service(settings: Annotated[Settings, Depends(get_settings)]) -> RAGService:
    return RAGService(create_llm_provider(settings), MockRetriever())


@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    request: RAGQueryRequest,
    _user: CurrentUser,
    service: Annotated[RAGService, Depends(get_rag_service)],
):
    return await service.query(request)
