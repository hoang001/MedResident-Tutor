"""Question-bank writes reuse the imported entities; callers own one transaction."""

import re
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.common.enums import QuestionType
from app.core.exceptions import AppError
from app.integration.reader import medical_payload
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.practice.contracts import EvaluationRequest
from app.modules.questions.models import (
    Question,
    Rubric,
    RubricCriterion,
    RubricCriterionSourceUnit,
)

REVIEW = {
    "status": "unverified",
    "reason": "Application editing/publication is not expert approval",
}


def new_id(kind):
    return f"APP_{kind}_{uuid.uuid4().hex}"


def issue(message, loc=("body", "criteria")):
    raise AppError(
        "QUESTION_NOT_READY",
        message,
        422,
        [{"loc": list(loc), "type": "question_bank", "msg": message}],
    )


def source_view(s, d, excerpt=False):
    meta = s.import_metadata or {}
    review = meta.get("expert_review") or {"status": "unverified"}
    return {
        "source_unit_id": s.external_id,
        "source_id": d.external_id,
        "title": s.title,
        "content": s.content[:300] if excerpt else s.content,
        "source_title": d.name,
        "pdf_page_start": s.pdf_page_start,
        "pdf_page_end": s.pdf_page_end,
        "printed_page_start": s.printed_page_start,
        "printed_page_end": s.printed_page_end,
        "chapter": s.chapter,
        "section": s.section,
        "subsection": s.subsection,
        "review": review,
        "metadata_errors": source_errors(s, d),
    }


def source_errors(s, d):
    errors = []
    if not all(
        isinstance(x, str) and x.strip()
        for x in (s.external_id, s.title, s.content, d.external_id, d.name)
    ):
        errors.append("Source identity, title or content missing")
    if not re.fullmatch(r"[0-9a-f]{64}", d.source_sha256 or ""):
        errors.append("Source SHA-256 missing")
    if s.pdf_page_start < 1 or s.pdf_page_end < s.pdf_page_start:
        errors.append("Invalid PDF locator")
    review = (s.import_metadata or {}).get("expert_review", {})
    if (
        not isinstance(review, dict)
        or not isinstance(review.get("status"), str)
        or not review["status"].strip()
    ):
        errors.append("Evidence review status not recorded")
    return errors


async def get_question(session, external_id, lock=False):
    query = select(Question).where(Question.external_id == external_id)
    if lock:
        query = query.with_for_update()
    q = await session.scalar(query)
    if q is None:
        raise HTTPException(404, "Question not found")
    return q


async def detail(session, question):
    r = await session.scalar(select(Rubric).where(Rubric.question_id == question.id))
    criteria = []
    if r:
        cs = await session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_id == r.id)
            .order_by(RubricCriterion.criterion_order, RubricCriterion.external_id)
        )
        for c in cs:
            rows = (
                await session.execute(
                    select(SourceUnit, Document)
                    .join(Document, Document.id == SourceUnit.document_id)
                    .join(
                        RubricCriterionSourceUnit,
                        RubricCriterionSourceUnit.source_unit_id == SourceUnit.id,
                    )
                    .where(RubricCriterionSourceUnit.criterion_id == c.id)
                    .order_by(RubricCriterionSourceUnit.evidence_order)
                )
            ).all()
            criteria.append(
                {
                    "criterion_id": c.external_id,
                    "description": c.description,
                    "max_score": c.score,
                    "source_unit_ids": [s.external_id for s, _ in rows],
                    "evidence": [source_view(s, d, True) for s, d in rows],
                }
            )
    return {
        "question_id": question.external_id,
        "content": question.content,
        "version": question.bank_version,
        "is_available": question.is_available,
        "topic_id": str(question.topic_id) if question.topic_id else None,
        "rubric_id": r.external_id if r else None,
        "rubric_name": r.name if r else "",
        "max_score": r.max_score if r else 0,
        "criteria": criteria,
        "review": (question.import_metadata or {}).get("bank_review", REVIEW),
        "rubric_review": (r.import_metadata or {}).get("bank_review", REVIEW) if r else REVIEW,
    }


async def validate_mapping(session, body):
    ids = {sid for c in body.criteria for sid in c.source_unit_ids}
    rows = (
        await session.execute(
            select(SourceUnit, Document)
            .join(Document, Document.id == SourceUnit.document_id)
            .where(SourceUnit.external_id.in_(ids))
        )
    ).all()
    found = {s.external_id: (s, d) for s, d in rows}
    for index, c in enumerate(body.criteria):
        for sid in c.source_unit_ids:
            if sid not in found:
                issue(
                    "Referenced evidence does not exist",
                    ("body", "criteria", index, "source_unit_ids"),
                )
            errors = source_errors(*found[sid])
            if errors:
                issue("; ".join(errors), ("body", "criteria", index, "source_unit_ids"))
    return {sid: s.id for sid, (s, _) in found.items()}


async def save(session, admin_id, body, external_id=None):
    mapping = await validate_mapping(session, body)
    if external_id:
        q = await get_question(session, external_id, lock=True)
        if body.version != q.bank_version:
            raise HTTPException(
                409, "Question was changed by another administrator; reload before editing"
            )
        q.bank_version += 1
        q.content = body.content.strip()
        q.import_metadata = {**(q.import_metadata or {}), "bank_review": REVIEW}
        r = await session.scalar(select(Rubric).where(Rubric.question_id == q.id))
    else:
        if body.version is not None or any(c.criterion_id for c in body.criteria):
            issue("New question/criteria IDs are generated by the server")
        q = Question(
            external_id=new_id("Q"),
            content=body.content.strip(),
            question_type=QuestionType.SHORT_ANSWER,
            topic_id=None,
            created_by=admin_id,
            is_available=False,
            bank_version=1,
            import_metadata={"origin": "admin_ui", "bank_review": REVIEW},
        )
        session.add(q)
        await session.flush()
        r = None
    if r is None:
        r = Rubric(
            question_id=q.id,
            external_id=new_id("R"),
            name=body.rubric_name.strip(),
            max_score=body.max_score,
            import_metadata={
                "origin": "admin_ui",
                "bank_review": REVIEW,
                "dataset_fields": {
                    "schema_version": "1.0.0",
                    "course_id": None,
                    "topic_id": None,
                    "scoring_rule": "sum_criterion_scores",
                    "validation_status": "unreviewed",
                    "expert_review_required": True,
                    "expert_review_reason": "Expert review has not been verified",
                },
            },
        )
        session.add(r)
        await session.flush()
    r.name, r.max_score = body.rubric_name.strip(), body.max_score
    r.import_metadata = {**(r.import_metadata or {}), "bank_review": REVIEW}
    old = {
        c.external_id: c
        for c in await session.scalars(
            select(RubricCriterion).where(RubricCriterion.rubric_id == r.id)
        )
    }
    for c in body.criteria:
        if c.criterion_id is not None and c.criterion_id not in old:
            issue("Criterion ID does not belong to this rubric")
    keep = {c.criterion_id for c in body.criteria if c.criterion_id}
    # Delete and recreate only mappings; preserved criterion IDs/UUIDs remain stable.
    for cid, c in old.items():
        await session.execute(
            delete(RubricCriterionSourceUnit).where(RubricCriterionSourceUnit.criterion_id == c.id)
        )
        if cid not in keep:
            await session.delete(c)
    await session.flush()
    for order, item in enumerate(body.criteria, 1):
        c = old.get(item.criterion_id)
        if c is None:
            c = RubricCriterion(
                rubric_id=r.id,
                external_id=new_id("C"),
                description=item.description.strip(),
                score=item.max_score,
                criterion_order=order,
                import_metadata={
                    "origin": "admin_ui",
                    "dataset_fields": {"acceptable_variants": [], "common_incorrect_claims": []},
                },
            )
            session.add(c)
        c.description, c.score, c.criterion_order = item.description.strip(), item.max_score, order
        await session.flush()
        for evidence_order, sid in enumerate(item.source_unit_ids, 1):
            session.add(
                RubricCriterionSourceUnit(
                    criterion_id=c.id, source_unit_id=mapping[sid], evidence_order=evidence_order
                )
            )
    await session.flush()
    await readiness(session, q)
    return await detail(session, q)


async def readiness(session, q):
    try:
        payload = await medical_payload(session, q.external_id, "Readiness validation only")
        EvaluationRequest.model_validate(payload)
        r = await session.scalar(select(Rubric).where(Rubric.question_id == q.id))
        rows = (
            await session.execute(
                select(SourceUnit, Document)
                .join(Document, Document.id == SourceUnit.document_id)
                .join(
                    RubricCriterionSourceUnit,
                    RubricCriterionSourceUnit.source_unit_id == SourceUnit.id,
                )
                .join(RubricCriterion, RubricCriterion.id == RubricCriterionSourceUnit.criterion_id)
                .where(RubricCriterion.rubric_id == r.id)
            )
        ).all()
        if any(source_errors(s, d) for s, d in rows):
            issue("Evidence metadata is incomplete")
    except ValueError:
        issue("Question, rubric or evidence is not ready for practice")
