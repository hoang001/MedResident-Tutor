from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.core.database import SessionFactory
from app.modules.auth.dependencies import AdminUser
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.questions.models import Question
from app.modules.questions.schemas import AvailabilityEdit, QuestionEdit
from app.modules.questions.service import detail, get_question, readiness, save, source_view

router = APIRouter(prefix="/admin", tags=["question-bank"])


@router.get("/questions")
async def list_questions(
    admin: AdminUser,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    async with SessionFactory() as s:
        query = select(Question).where(Question.external_id.is_not(None))
        if q:
            query = query.where(
                or_(
                    Question.content.icontains(q, autoescape=True),
                    Question.external_id.icontains(q, autoescape=True),
                )
            )
        rows = await s.scalars(
            query.order_by(Question.created_at.desc(), Question.external_id)
            .limit(limit)
            .offset(offset)
        )
        return [
            {
                "question_id": x.external_id,
                "content": x.content,
                "is_available": x.is_available,
                "version": x.bank_version,
            }
            for x in rows
        ]


@router.post("/questions", status_code=201)
async def create_question(body: QuestionEdit, admin: AdminUser):
    async with SessionFactory() as s, s.begin():
        return await save(s, admin.id, body)


@router.get("/questions/{question_id}")
async def question_detail(question_id: str, admin: AdminUser):
    async with SessionFactory() as s:
        return await detail(s, await get_question(s, question_id))


@router.put("/questions/{question_id}")
async def edit_question(question_id: str, body: QuestionEdit, admin: AdminUser):
    async with SessionFactory() as s, s.begin():
        return await save(s, admin.id, body, question_id)


@router.patch("/questions/{question_id}/availability")
async def availability(question_id: str, body: AvailabilityEdit, admin: AdminUser):
    from fastapi import HTTPException

    async with SessionFactory() as s, s.begin():
        question = await get_question(s, question_id, lock=True)
        if question.bank_version != body.version:
            raise HTTPException(409, "Question changed; reload before changing availability")
        if body.is_available:
            await readiness(s, question)
        question.is_available = body.is_available
        question.bank_version += 1
        return await detail(s, question)


@router.get("/source-units")
async def source_units(
    admin: AdminUser,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    async with SessionFactory() as s:
        query = select(SourceUnit, Document).join(Document, Document.id == SourceUnit.document_id)
        if q:
            query = query.where(
                or_(
                    SourceUnit.title.icontains(q, autoescape=True),
                    SourceUnit.content.icontains(q, autoescape=True),
                    SourceUnit.external_id.icontains(q, autoescape=True),
                    Document.name.icontains(q, autoescape=True),
                )
            )
        rows = (
            await s.execute(query.order_by(SourceUnit.external_id).limit(limit).offset(offset))
        ).all()
        return [source_view(a, b, True) for a, b in rows]


@router.get("/source-units/{source_unit_id}")
async def source_unit_detail(source_unit_id: str, admin: AdminUser):
    from fastapi import HTTPException

    async with SessionFactory() as s:
        row = (
            await s.execute(
                select(SourceUnit, Document)
                .join(Document, Document.id == SourceUnit.document_id)
                .where(SourceUnit.external_id == source_unit_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(404, "SourceUnit not found")
        return source_view(*row)
