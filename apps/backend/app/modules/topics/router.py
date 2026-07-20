import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import AdminUser, CurrentUser
from app.modules.topics.schemas import TopicCreate, TopicResponse
from app.modules.topics.service import TopicService

router = APIRouter(prefix="/topics", tags=["topics"])


def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> TopicService:
    return TopicService(session)


@router.get("", response_model=list[TopicResponse])
async def list_topics(
    _user: CurrentUser,
    service: Annotated[TopicService, Depends(get_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list(limit, offset)


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(
    data: TopicCreate,
    _admin: AdminUser,
    service: Annotated[TopicService, Depends(get_service)],
):
    return await service.create(data)


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(
    topic_id: uuid.UUID,
    _user: CurrentUser,
    service: Annotated[TopicService, Depends(get_service)],
):
    return await service.get(topic_id)
