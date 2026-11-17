import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.modules.auth.dependencies import bearer, get_current_user
from app.modules.practice.assets import authored_metadata, image_response, learner_view
from app.modules.practice.contracts import ServiceError
from app.modules.practice.models import PracticeAttempt
from app.modules.practice.providers import get_provider
from app.modules.practice.service import owned, process, submit, view
from app.modules.practice.structured import definition
from app.modules.practice.structured import learner_view as structured_view
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
    student_answer: str | None = Field(default=None, min_length=1, max_length=16000)
    structured_answers: dict[str, str | None] | None = Field(default=None, max_length=8)
    revision_id: str | None = Field(default=None, min_length=1, max_length=255)


def provider():
    try:
        return get_provider(get_settings())
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from None


@router.get("/config")
async def config(user: CurrentUser):
    try:
        mode = provider().mode
    except HTTPException:
        # Structured exercises remain available without any Medical/Teaching configuration.
        mode = "unavailable"
    result = {"execution_mode": mode}
    settings = get_settings()
    if mode == "http":
        result["request_timeout_ms"] = settings.practice_request_timeout_ms()
    return result


async def all_questions():
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
                or_(
                    ~select(RubricCriterion.id)
                    .where(RubricCriterion.rubric_id == Rubric.id, ~eligible)
                    .exists(),
                    (
                        Question.import_metadata["dataset_fields"]["retrieval_scope"].as_string()
                        == "textbook"
                    )
                    if get_settings().practice_retrieval_strategy != "prelinked"
                    else False,
                ),
            )
            .order_by(Question.external_id)
        )
        rows = await session.scalars(query)
        result = []
        for q in rows:
            item = {"question_id": q.external_id, "question": q.content}
            if topic_name := (q.import_metadata or {}).get("authoring", {}).get("topic"):
                item["topic"] = topic_name
            exercise = definition(q.import_metadata)
            if exercise:
                item["structured_exercise"] = structured_view(exercise)
            authored = authored_metadata(q.import_metadata)
            if authored:
                item["clinical_exercise"] = learner_view(
                    authored,
                    "/practice/questions/" + q.external_id,
                    structured=exercise is not None,
                )
                if exercise:
                    item["question"] = (
                        authored["learner"]["presentation"]
                        + "\n\n"
                        + "\n".join(part.label for part in exercise.parts)
                    )
            result.append(item)
        return result


def filtered(items, topic, q):
    import unicodedata

    def normalize(value):
        return "".join(
            c
            for c in unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
            if unicodedata.category(c) != "Mn"
        )

    needle = normalize(q.strip())
    return [
        x
        for x in items
        if (not topic or x.get("topic", "Ca bệnh và câu hỏi đã có") == topic)
        and (not needle or needle in normalize(x["question"] + " " + x["question_id"]))
    ]


@router.get("/questions")
async def questions(
    user: CurrentUser,
    topic: str = "",
    q: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return filtered(await all_questions(), topic, q)[offset : offset + limit]


@router.get("/catalog")
async def catalog(
    user: CurrentUser,
    topic: Annotated[str, Query(max_length=200)] = "",
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    from collections import Counter

    items = await all_questions()
    counts = Counter(x.get("topic", "Ca bệnh và câu hỏi đã có") for x in items)
    matches = filtered(items, topic, q)
    page = matches[offset : offset + limit]
    # Student-owned progress metadata only; never return rubric/answer from here.
    ids = [x["question_id"] for x in page]
    async with SessionFactory() as session:
        rows = await session.scalars(
            select(PracticeAttempt)
            .where(
                PracticeAttempt.user_id == user.id,
                PracticeAttempt.snapshot["payload"]["rubric"]["question_id"].as_string().in_(ids),
            )
            .order_by(PracticeAttempt.created_at.desc(), PracticeAttempt.id)
        )
        latest = {}
        for row in rows:
            key = row.snapshot["payload"]["rubric"]["question_id"]
            if key not in latest:
                latest[key] = row
        for item in page:
            if row := latest.get(item["question_id"]):
                item["attempt_status"] = row.status
                item["last_attempt_id"] = str(row.id)
    return dict(
        items=page,
        total=len(matches),
        available_total=len(items),
        offset=offset,
        limit=limit,
        topics=[dict(name=name, count=count) for name, count in sorted(counts.items())],
    )


@router.get("/questions/{question_id}")
async def question(question_id: str, user: CurrentUser):
    for item in await all_questions():
        if item["question_id"] == question_id:
            return item
    raise HTTPException(404, "Question not available")


@router.get("/questions/{question_id}/assets/{asset_id}")
async def question_asset(question_id: str, asset_id: str, user: CurrentUser):
    async with SessionFactory() as session:
        q = await session.scalar(
            select(Question).where(
                Question.external_id == question_id, Question.is_available.is_(True)
            )
        )
        if q is None:
            raise HTTPException(404, "Question not available")
        authored = authored_metadata(q.import_metadata)
    return await image_response(authored, asset_id, get_settings().file_storage_path)


@router.post("/attempts")
async def create(
    body: Submission, user: CurrentUser, idempotency_key: str = Header(min_length=1, max_length=128)
):
    attempt_id, created = await submit(
        SessionFactory,
        user.id,
        body.question_id,
        body.student_answer,
        idempotency_key,
        provider,
        structured_answers=body.structured_answers,
        revision_id=body.revision_id,
        retrieval_settings=get_settings(),
    )
    async with SessionFactory() as session:
        row = await owned(session, user.id, attempt_id)
        if row.execution_mode == "structured":
            return view(row)
    if created:
        await process(
            SessionFactory, user.id, attempt_id, provider(), get_settings().practice_stage_deadline
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


@router.get("/history")
async def history_catalog(
    user: CurrentUser,
    q: Annotated[str, Query(max_length=200)] = "",
    status: Literal["all", "completed", "processing", "attention"] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 15,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    async with SessionFactory() as session:
        base = select(PracticeAttempt).where(PracticeAttempt.user_id == user.id)
        query = base
        if status == "completed":
            query = query.where(PracticeAttempt.status == "completed")
        elif status == "processing":
            query = query.where(
                PracticeAttempt.status.in_(["pending", "medical_running", "teaching_running"])
            )
        elif status == "attention":
            query = query.where(PracticeAttempt.status.in_(["medical_failed", "teaching_failed"]))
        if q:
            query = query.where(
                PracticeAttempt.snapshot["payload"]["question"]
                .as_string()
                .icontains(q, autoescape=True)
            )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        overall = await session.scalar(select(func.count()).select_from(base.subquery()))
        completed = await session.scalar(
            select(func.count()).select_from(
                base.where(PracticeAttempt.status == "completed").subquery()
            )
        )
        rows = await session.scalars(
            query.order_by(PracticeAttempt.created_at.desc(), PracticeAttempt.id)
            .limit(limit)
            .offset(offset)
        )
        return {
            "total": total,
            "overall_total": overall,
            "completed_total": completed,
            "items": [view(row) for row in rows],
        }


@router.get("/attempts/{attempt_id}")
async def result(attempt_id: uuid.UUID, user: CurrentUser):
    async with SessionFactory() as session:
        return view(await owned(session, user.id, attempt_id))


@router.get("/attempts/{attempt_id}/assets/{asset_id}")
async def attempt_asset(attempt_id: uuid.UUID, asset_id: str, user: CurrentUser):
    async with SessionFactory() as session:
        row = await owned(session, user.id, attempt_id)
        authored = row.snapshot.get("clinical_exercise")
    return await image_response(authored, asset_id, get_settings().file_storage_path)


@router.post("/attempts/{attempt_id}/retry")
async def retry(attempt_id: uuid.UUID, user: CurrentUser):
    async with SessionFactory() as session:
        row = await owned(session, user.id, attempt_id)
        if row.execution_mode == "structured":
            return view(row)  # Atomic completed result: no provider and no second grade.
    await process(
        SessionFactory,
        user.id,
        attempt_id,
        provider(),
        get_settings().practice_stage_deadline,
        retry=True,
    )
    async with SessionFactory() as session:
        return view(await owned(session, user.id, attempt_id))
