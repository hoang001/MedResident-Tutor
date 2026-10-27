import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.modules.auth.dependencies import bearer, get_current_user
from app.modules.practice.contracts import ServiceError
from app.modules.practice.models import PracticeAttempt
from app.modules.practice.providers import get_provider
from app.modules.practice.service import owned, process, submit, view
from app.modules.questions.models import (
    Question,
    Rubric,
    RubricCriterion,
    RubricCriterionSourceUnit,
)
from app.modules.users.models import User


async def practice_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    # Close the authentication read transaction before waiting for providers.
    async with SessionFactory() as session:
        user = await get_current_user(credentials, session, get_settings())
        session.expunge(user)
        return user


CurrentUser = Annotated[User, Depends(practice_user)]

router = APIRouter(prefix="/practice", tags=["practice"])


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=255)
    student_answer: str = Field(min_length=1, max_length=16000)


def provider():
    try:
        return get_provider(get_settings())
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from None


@router.get("/config")
async def config(user: CurrentUser):
    return {"execution_mode": provider().mode}


@router.get("/questions")
async def questions(user: CurrentUser):
    async with SessionFactory() as session:
        # Imported questions with directly mapped evidence, no topic required.
        eligible = (
            select(RubricCriterionSourceUnit.criterion_id)
            .where(RubricCriterionSourceUnit.criterion_id == RubricCriterion.id)
            .exists()
        )
        query = (
            select(Question)
            .join(Rubric)
            .where(
                Question.external_id.is_not(None),
                Question.is_available.is_(True),
                select(RubricCriterion.id).where(RubricCriterion.rubric_id == Rubric.id).exists(),
                ~select(RubricCriterion.id)
                .where(RubricCriterion.rubric_id == Rubric.id, ~eligible)
                .exists(),
            )
            .order_by(Question.external_id)
        )
        rows = await session.scalars(query)
        return [{"question_id": q.external_id, "question": q.content} for q in rows]


@router.get("/questions/{question_id}")
async def question(question_id: str, user: CurrentUser):
    for item in await questions(user):
        if item["question_id"] == question_id:
            return item
    raise HTTPException(404, "Question not available")


@router.post("/attempts")
async def create(
    body: Submission, user: CurrentUser, idempotency_key: str = Header(min_length=1, max_length=128)
):
    if not body.student_answer.strip():
        raise HTTPException(422, "Student answer is empty")
    p = provider()
    attempt_id, created = await submit(
        SessionFactory, user.id, body.question_id, body.student_answer, idempotency_key, p
    )
    if created:
        await process(
            SessionFactory, user.id, attempt_id, p, get_settings().practice_timeout_seconds
        )
    async with SessionFactory() as session:
        return view(await owned(session, user.id, attempt_id))


@router.get("/attempts")
async def history(user: CurrentUser):
    async with SessionFactory() as session:
        rows = await session.scalars(
            select(PracticeAttempt)
            .where(PracticeAttempt.user_id == user.id)
            .order_by(PracticeAttempt.created_at.desc())
            .limit(100)
        )
        return [view(row) for row in rows]


@router.get("/attempts/{attempt_id}")
async def result(attempt_id: uuid.UUID, user: CurrentUser):
    async with SessionFactory() as session:
        return view(await owned(session, user.id, attempt_id))


@router.post("/attempts/{attempt_id}/retry")
async def retry(attempt_id: uuid.UUID, user: CurrentUser):
    await process(
        SessionFactory,
        user.id,
        attempt_id,
        provider(),
        get_settings().practice_timeout_seconds,
        retry=True,
    )
    async with SessionFactory() as session:
        return view(await owned(session, user.id, attempt_id))
