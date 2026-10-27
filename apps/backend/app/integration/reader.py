"""Build the Medical pilot's four-field input, without inference or gold answers."""

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integration.inputs import require
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.questions.models import (
    Question,
    Rubric,
    RubricCriterion,
    RubricCriterionSourceUnit,
)

RUBRIC_FIELDS = (
    "schema_version",
    "course_id",
    "topic_id",
    "scoring_rule",
    "validation_status",
    "expert_review_required",
    "expert_review_reason",
)
CRITERION_FIELDS = ("acceptable_variants", "common_incorrect_claims")


async def medical_payload(
    session: AsyncSession, question_external_id: str, student_answer: str
) -> dict:
    require(
        isinstance(student_answer, str) and bool(student_answer.strip()), "Empty student answer"
    )
    q = await session.scalar(select(Question).where(Question.external_id == question_external_id))
    require(q is not None, "Question not found")
    r = await session.scalar(select(Rubric).where(Rubric.question_id == q.id))
    require(r is not None and bool(r.external_id), "Imported rubric not found")
    criteria = list(
        await session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_id == r.id)
            .order_by(RubricCriterion.criterion_order, RubricCriterion.external_id)
        )
    )
    require(
        bool(criteria) and len({c.criterion_order for c in criteria}) == len(criteria),
        "Missing criteria or ambiguous criterion order",
    )
    require(
        all(c.external_id and math.isfinite(c.score) and c.score > 0 for c in criteria)
        and math.isfinite(r.max_score)
        and math.isclose(sum(c.score for c in criteria), r.max_score, rel_tol=0, abs_tol=1e-9),
        "Invalid rubric scores",
    )
    rubric_fields = (r.import_metadata or {}).get("dataset_fields", {})
    require(all(key in rubric_fields for key in RUBRIC_FIELDS), "Missing rubric dataset fields")
    rubric = {key: rubric_fields[key] for key in RUBRIC_FIELDS}
    rubric.update(
        rubric_id=r.external_id, question_id=q.external_id, max_score=r.max_score, criteria=[]
    )
    evidence = []
    seen = set()
    for c in criteria:
        rows = (
            await session.execute(
                select(RubricCriterionSourceUnit, SourceUnit, Document)
                .join(SourceUnit, SourceUnit.id == RubricCriterionSourceUnit.source_unit_id)
                .join(Document, Document.id == SourceUnit.document_id)
                .where(RubricCriterionSourceUnit.criterion_id == c.id)
                .order_by(RubricCriterionSourceUnit.evidence_order, SourceUnit.external_id)
            )
        ).all()
        require(bool(rows), "Criterion has no evidence")
        fields = (c.import_metadata or {}).get("dataset_fields", {})
        require(all(key in fields for key in CRITERION_FIELDS), "Missing criterion dataset fields")
        item = {key: fields[key] for key in CRITERION_FIELDS}
        item.update(
            criterion_id=c.external_id,
            description=c.description,
            max_score=c.score,
            required_source_unit_ids=[],
        )
        for _, su, document in rows:
            require(
                bool(su.external_id) and bool(document.external_id) and bool(su.content.strip()),
                "Evidence identity/content missing",
            )
            item["required_source_unit_ids"].append(su.external_id)
            if su.id not in seen:
                seen.add(su.id)
                evidence.append(
                    {
                        "source_unit_id": su.external_id,
                        "source_id": document.external_id,
                        "title": su.title,
                        "page_start": su.pdf_page_start,
                        "page_end": su.pdf_page_end,
                        "content": su.content,
                    }
                )
        rubric["criteria"].append(item)
    return {
        "question": q.content,
        "student_answer": student_answer,
        "rubric": rubric,
        "evidence": evidence,
    }
