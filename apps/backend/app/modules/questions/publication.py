"""Shared transactional publication for the admin UI and authorized batch imports."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.ai.retrieval.evidence import digest
from app.integration.reader import medical_payload
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.questions.service import get_question, readiness


async def publish(session, question, actor_id, *, review=None):
    """Caller locks question and owns transaction; review never implies clinical approval."""
    await readiness(session, question)
    metadata = question.import_metadata or {}
    if metadata.get("superseded_by"):
        raise HTTPException(409, "This revision was superseded")
    if metadata.get("origin") == "admin_ui" and not metadata.get("approved_package"):
        if not (question.reference_answer or "").strip():
            raise HTTPException(422, "Reference answer required before publication")
        payload = await medical_payload(session, question.external_id, "Snapshot assembly")
        payload["rubric"]["reference_answer"] = question.reference_answer
        payload["rubric"]["reference_answer_usage"] = (
            "Reference wording is illustrative, not the only valid answer; "
            "grade supported meaning against criteria and source evidence."
        )
        package = dict(
            schema_version="approved-package-v1",
            revision_id=question.external_id,
            question_version=question.bank_version,
            payload=payload,
            reference_answer=question.reference_answer,
            approved_by=review["actor"] if review else str(actor_id),
            approved_at=datetime.now(UTC).isoformat(),
            expert_verified=False,
        )
        if review:
            package["source_review"] = review
            package["import_account_id"] = str(actor_id)  # FK/audit account, not a human reviewer.
        ids = [e["source_unit_id"] for e in payload["evidence"]]
        rows = (
            await session.execute(
                select(SourceUnit, Document)
                .join(Document, Document.id == SourceUnit.document_id)
                .where(SourceUnit.external_id.in_(ids))
                .order_by(SourceUnit.external_id)
            )
        ).all()
        package["provenance"] = [
            dict(
                source_unit_id=u.external_id,
                source_id=d.external_id,
                sha256=d.source_sha256,
                pdf_page_start=u.pdf_page_start,
                pdf_page_end=u.pdf_page_end,
                printed_page_start=u.printed_page_start,
                printed_page_end=u.printed_page_end,
                source_unit_metadata=u.import_metadata,
                document_metadata=d.import_metadata,
            )
            for u, d in rows
        ]
        package["sha256"] = digest(package)
        question.import_metadata = {**metadata, "approved_package": package}
        if previous := metadata.get("previous_revision"):
            old = await get_question(session, previous, lock=True)
            if (old.import_metadata or {}).get("superseded_by"):
                raise HTTPException(409, "Previous revision was already superseded")
            old.is_available = False
            old.import_metadata = {**old.import_metadata, "superseded_by": question.external_id}
    question.is_available = True
    question.bank_version += 1
