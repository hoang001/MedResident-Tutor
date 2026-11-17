import hashlib
import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import get_db
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.modules.auth.dependencies import AdminUser, CurrentUser
from app.modules.knowledge.router import Graph
from app.modules.study.models import KnowledgeReview, StudyRecord, StudySession
from app.modules.study.questions import question_bank, question_view, search_questions
from app.modules.users.models import User

router = APIRouter(prefix="/study", tags=["study"])
DB = Annotated[AsyncSession, Depends(get_db)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordInput(Input):
    node_id: str = Field(min_length=1, max_length=300)
    version: int = Field(ge=0)
    read_state: Literal["unread", "reading", "read"]
    bookmarked: bool
    note: str = Field(default="", max_length=4000)


class SessionInput(Input):
    idempotency_key: uuid.UUID
    question_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("question_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value) or any(not (1 <= len(v) <= 300) for v in value):
            raise ValueError("Invalid question selection")
        return value


class AnswerInput(Input):
    version: int = Field(ge=1)
    answers: dict[str, str] = Field(max_length=20)
    submit: bool = False

    @field_validator("answers")
    @classmethod
    def bounded_answers(cls, value):
        if any(len(k) > 300 or len(v) > 16000 for k, v in value.items()):
            raise ValueError("Answer is too long")
        return value


class ReviewInput(Input):
    node_id: str = Field(min_length=1, max_length=300)
    revision: str = Field(min_length=64, max_length=64)
    status: Literal["needs_review", "source_checked", "needs_correction"]
    note: str = Field(min_length=1, max_length=4000)


async def commit(db: AsyncSession):
    try:
        await db.commit()
    except (IntegrityError, StaleDataError) as exc:
        await db.rollback()
        raise ConflictError("STUDY_CONFLICT", "Data changed; reload before saving") from exc


def record_view(row: StudyRecord):
    return {
        key: getattr(row, key)
        for key in (
            "node_id",
            "title",
            "revision",
            "read_state",
            "bookmarked",
            "note",
            "version",
            "updated_at",
        )
    }


def session_view(row: StudySession):
    return {
        key: getattr(row, key)
        for key in ("id", "status", "questions", "answers", "version", "created_at", "updated_at")
    } | {
        "questions": [
            question_view(q, show_basis=row.status == "submitted") for q in row.questions
        ],
        "graded": False,
        "score": None,
    }


async def available_questions(snapshot, db):
    """A current source-correction flag excludes fresh questions, not saved sessions."""
    blocked, seen = set(), set()
    rows = await db.scalars(
        select(KnowledgeReview).order_by(
            KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc()
        )
    )
    for row in rows:
        key = (row.node_id, row.revision)
        node = snapshot.nodes.get(row.node_id)
        if key in seen or not node or row.revision != node["revision"]:
            continue
        seen.add(key)
        if row.status == "needs_correction":
            blocked.add(row.node_id)
    return {
        key: q
        for key, q in question_bank(snapshot).items()
        if not set(q.get("node_ids", [])) & blocked
    }


@router.get("/questions")
async def questions(
    user: CurrentUser,
    db: DB,
    graph: Graph,
    q: str = Query(default="", max_length=200),
    book: str = Query(default="", max_length=100),
    chapter: int | None = Query(default=None, ge=1),
    origin: Literal["all", "book", "kg"] = "all",
    focus: Literal["all", "read", "bookmarked"] = "all",
    node_id: str = Query(default="", max_length=300),
    offset: int = Query(default=0, ge=0, le=20000),
    limit: int = Query(default=20, ge=1, le=50),
):
    snapshot = await graph.snapshot()
    selected_nodes = None
    if focus != "all":
        predicate = (
            StudyRecord.read_state == "read"
            if focus == "read"
            else StudyRecord.bookmarked.is_(True)
        )
        records = (
            await db.execute(
                select(StudyRecord.node_id, StudyRecord.revision).where(
                    StudyRecord.user_id == user.id, predicate
                )
            )
        ).all()
        selected_nodes = {
            node
            for node, revision in records
            if node in snapshot.nodes
            and (focus != "read" or snapshot.nodes[node]["revision"] == revision)
        }
    if node_id:
        snapshot.get(node_id)
        selected_nodes = {node_id} if selected_nodes is None else selected_nodes & {node_id}
    rows = search_questions(
        await available_questions(snapshot, db),
        q=q,
        book=book,
        chapter=chapter,
        origin=origin,
        node_ids=selected_nodes,
    )
    return {
        "total": len(rows),
        "items": [question_view(r) for r in rows[offset : offset + limit]],
        "graded": False,
        "expert_verified": False,
        "model_called": False,
        "selection_basis": focus,
    }


@router.get("/summary")
async def summary(user: CurrentUser, db: DB):
    states = dict(
        (
            await db.execute(
                select(StudyRecord.read_state, func.count())
                .where(StudyRecord.user_id == user.id)
                .group_by(StudyRecord.read_state)
            )
        ).all()
    )
    bookmarked = await db.scalar(
        select(func.count())
        .select_from(StudyRecord)
        .where(StudyRecord.user_id == user.id, StudyRecord.bookmarked.is_(True))
    )
    sessions = dict(
        (
            await db.execute(
                select(StudySession.status, func.count())
                .where(StudySession.user_id == user.id)
                .group_by(StudySession.status)
            )
        ).all()
    )
    recent = (
        await db.scalars(
            select(StudyRecord)
            .where(StudyRecord.user_id == user.id)
            .order_by(StudyRecord.updated_at.desc())
            .limit(5)
        )
    ).all()
    return {
        "reading": states.get("reading", 0),
        "read": states.get("read", 0),
        "bookmarked": bookmarked,
        "drafts": sessions.get("draft", 0),
        "submitted": sessions.get("submitted", 0),
        "recent": [record_view(r) for r in recent],
        "mastery_assessed": False,
    }


@router.get("/records")
async def records(
    user: CurrentUser,
    db: DB,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    bookmarked: bool = False,
):
    query = select(StudyRecord).where(StudyRecord.user_id == user.id)
    if bookmarked:
        query = query.where(StudyRecord.bookmarked.is_(True))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(query.order_by(StudyRecord.updated_at.desc()).offset(offset).limit(limit))
    ).all()
    return {"total": total, "items": [record_view(r) for r in rows]}


@router.get("/record")
async def record(user: CurrentUser, db: DB, node_id: str = Query(max_length=300)):
    row = await db.scalar(
        select(StudyRecord).where(StudyRecord.user_id == user.id, StudyRecord.node_id == node_id)
    )
    return (
        record_view(row)
        if row
        else {
            "node_id": node_id,
            "version": 0,
            "read_state": "unread",
            "bookmarked": False,
            "note": "",
            "revision": "",
        }
    )


@router.put("/record")
async def save_record(payload: RecordInput, user: CurrentUser, db: DB, graph: Graph):
    node = (await graph.snapshot()).get(payload.node_id)
    row = await db.scalar(
        select(StudyRecord).where(
            StudyRecord.user_id == user.id, StudyRecord.node_id == payload.node_id
        )
    )
    if payload.version != (row.version if row else 0):
        raise ConflictError("STUDY_CONFLICT", "Reading record changed; reload before saving")
    if row is None:
        row = StudyRecord(user_id=user.id, node_id=payload.node_id)
        db.add(row)
    row.title, row.revision = node["title"], node["revision"]
    row.read_state, row.bookmarked, row.note = payload.read_state, payload.bookmarked, payload.note
    await commit(db)
    await db.refresh(row)
    return record_view(row)


@router.get("/sessions")
async def sessions(
    user: CurrentUser,
    db: DB,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    total = await db.scalar(
        select(func.count()).select_from(StudySession).where(StudySession.user_id == user.id)
    )
    rows = (
        await db.scalars(
            select(StudySession)
            .where(StudySession.user_id == user.id)
            .order_by(StudySession.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {k: v for k, v in session_view(r).items() if k not in ("questions", "answers")}
            | {
                "question_count": len(r.questions),
                "answered_count": sum(bool(a.strip()) for a in r.answers.values()),
            }
            for r in rows
        ],
    }


@router.post("/sessions", status_code=201)
async def create_session(payload: SessionInput, user: CurrentUser, db: DB, graph: Graph):
    digest = hashlib.sha256(json.dumps(payload.question_ids).encode()).hexdigest()
    existing = await db.scalar(
        select(StudySession).where(
            StudySession.user_id == user.id,
            StudySession.idempotency_key == str(payload.idempotency_key),
        )
    )
    if existing:
        if existing.input_hash != digest:
            raise ConflictError("STUDY_CONFLICT", "Idempotency key was used for another selection")
        return session_view(existing)
    snapshot = await graph.snapshot()
    bank = await available_questions(snapshot, db)
    questions = []
    for node_id in payload.question_ids:
        question = bank.get(node_id)
        if not question:
            if node_id.startswith("KGQ:"):
                raise ConflictError(
                    "STUDY_QUESTION_CHANGED", "Question changed; reload the question list"
                )
            snapshot.get(node_id)
            raise AppError("INVALID_STUDY_QUESTION", "Selection is not a study question", 422)
        questions.append(question)
    row = StudySession(
        user_id=user.id,
        idempotency_key=str(payload.idempotency_key),
        input_hash=digest,
        status="draft",
        questions=questions,
        answers={},
    )
    db.add(row)
    await commit(db)
    await db.refresh(row)
    return session_view(row)


async def owned_session(session_id, user, db):
    row = await db.scalar(
        select(StudySession).where(StudySession.id == session_id, StudySession.user_id == user.id)
    )
    if not row:
        raise NotFoundError("STUDY_SESSION_NOT_FOUND", "Study session not found")
    return row


@router.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, user: CurrentUser, db: DB):
    return session_view(await owned_session(session_id, user, db))


@router.put("/sessions/{session_id}")
async def save_session(session_id: uuid.UUID, payload: AnswerInput, user: CurrentUser, db: DB):
    row = await owned_session(session_id, user, db)
    if set(payload.answers) - {q["id"] for q in row.questions}:
        raise AppError("INVALID_STUDY_ANSWER", "Answer is outside this session", 422)
    if row.status == "submitted":
        if payload.submit and row.answers == payload.answers:
            return session_view(row)
        raise ConflictError("STUDY_SESSION_SUBMITTED", "Submitted sessions cannot be edited")
    if row.version != payload.version:
        raise ConflictError("STUDY_CONFLICT", "Session changed; reload before saving")
    row.answers = payload.answers
    if payload.submit:
        row.status = "submitted"
    await commit(db)
    await db.refresh(row)
    return session_view(row)


@router.get("/reviews")
async def reviews(user: CurrentUser, db: DB, graph: Graph, node_id: str = Query(max_length=300)):
    node = (await graph.snapshot()).get(node_id)
    rows = (
        await db.execute(
            select(KnowledgeReview, User.full_name)
            .join(User, KnowledgeReview.reviewer_id == User.id)
            .where(KnowledgeReview.node_id == node_id)
            .order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc())
            .limit(30)
        )
    ).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "note": r.note,
            "reviewer": name,
            "created_at": r.created_at,
            "revision": r.revision,
            "current": r.revision == node["revision"],
            "expert_approval": False,
        }
        for r, name in rows
    ]


@router.post("/reviews", status_code=201)
async def add_review(payload: ReviewInput, user: AdminUser, db: DB, graph: Graph):
    node = (await graph.snapshot()).get(payload.node_id)
    if node["revision"] != payload.revision:
        raise ConflictError("KNOWLEDGE_CHANGED", "Knowledge changed; reload before reviewing")
    row = KnowledgeReview(reviewer_id=user.id, **payload.model_dump())
    db.add(row)
    await commit(db)
    await db.refresh(row)
    return {"id": row.id, "status": row.status, "expert_approval": False}
