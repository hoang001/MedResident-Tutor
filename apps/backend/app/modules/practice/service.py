import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.integration.reader import medical_payload
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.practice.contracts import (
    EvaluationRequest,
    ServiceError,
    validate_output,
    validate_teaching,
)
from app.modules.practice.models import PracticeAttempt
from app.modules.questions.models import Question


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


async def owned(session, user_id, attempt_id, lock=False):
    query = select(PracticeAttempt).where(
        PracticeAttempt.id == attempt_id, PracticeAttempt.user_id == user_id
    )
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise HTTPException(404, "Practice attempt not found")
    return row


def view(row):
    return {
        "id": str(row.id),
        "question_id": row.snapshot["payload"]["rubric"]["question_id"],
        "question": row.snapshot["payload"]["question"],
        "student_answer": row.student_answer,
        "status": row.status,
        "execution_mode": row.execution_mode,
        "medical_evaluation": row.medical_evaluation,
        "teaching_feedback": row.teaching_feedback,
        "evidence": row.snapshot["payload"]["evidence"] if row.medical_evaluation else [],
        "provenance": row.snapshot["provenance"] if row.medical_evaluation else [],
        "snapshot_hash": row.snapshot["hash"],
        "provider_metadata": row.provider_metadata,
        "stage_error": row.stage_error,
        "created_at": row.created_at.isoformat(),
    }


async def submit(factory, user_id, question_external_id, answer, key, provider):
    input_hash = digest({"question_id": question_external_id, "student_answer": answer})
    async with factory() as session, session.begin():
        prior = await session.scalar(
            select(PracticeAttempt).where(
                PracticeAttempt.user_id == user_id, PracticeAttempt.idempotency_key == key
            )
        )
        if prior:
            if prior.input_hash != input_hash:
                raise HTTPException(409, "Idempotency key reused with different input")
            return prior.id, False
        question = await session.scalar(
            select(Question).where(Question.external_id == question_external_id).with_for_update()
        )
        if question is None or not question.is_available:
            raise HTTPException(404, "Question not found")
        payload = await medical_payload(session, question_external_id, answer)
        EvaluationRequest.model_validate(payload)
        ids = [e["source_unit_id"] for e in payload["evidence"]]
        rows = (
            await session.execute(
                select(SourceUnit, Document)
                .join(Document, SourceUnit.document_id == Document.id)
                .where(SourceUnit.external_id.in_(ids))
                .order_by(SourceUnit.external_id)
            )
        ).all()
        provenance = [
            dict(
                source_unit_id=s.external_id,
                source_id=d.external_id,
                sha256=d.source_sha256,
                pdf_page_start=s.pdf_page_start,
                pdf_page_end=s.pdf_page_end,
                printed_page_start=s.printed_page_start,
                printed_page_end=s.printed_page_end,
                source_unit_metadata=s.import_metadata,
                document_metadata=d.import_metadata,
            )
            for s, d in rows
        ]
        snapshot = {"payload": payload, "provenance": provenance}
        snapshot["hash"] = digest(snapshot)
        attempt_id = uuid.uuid4()
        result = await session.execute(
            insert(PracticeAttempt)
            .values(
                id=attempt_id,
                user_id=user_id,
                question_id=question.id,
                idempotency_key=key,
                input_hash=input_hash,
                student_answer=answer,
                status="pending",
                execution_mode=provider.mode,
                snapshot=snapshot,
                provider_metadata={},
            )
            .on_conflict_do_nothing(constraint="uq_practice_user_key")
            .returning(PracticeAttempt.id)
        )
        if result.scalar_one_or_none():
            return attempt_id, True
        prior = await session.scalar(
            select(PracticeAttempt).where(
                PracticeAttempt.user_id == user_id, PracticeAttempt.idempotency_key == key
            )
        )
        if prior.input_hash != input_hash:
            raise HTTPException(409, "Idempotency key reused with different input")
        return prior.id, False


def teaching_payload(payload, medical):
    # No learner state is inferred; taxonomy remains explicitly unverified.
    return {
        "schema_version": "1.0.0",
        "question": payload["question"],
        "student_answer": payload["student_answer"],
        "medical_evaluation": medical,
        "learner_context": {
            "mastery": [],
            "recurring_errors": [],
            "recent_improvements": [],
            "recent_attempts_summary": None,
        },
        "metadata": {
            "specialty": None,
            "course_group": None,
            "course_id": payload["rubric"].get("course_id"),
            "course_name": None,
            "specialty_level": None,
            "topic_id": None,
            "topic_name": None,
            "concept_ids": [],
        },
    }


async def process(factory, user_id, attempt_id, provider, timeout, retry=False):
    for _ in range(2):
        token = uuid.uuid4()
        async with factory() as session, session.begin():
            row = await owned(session, user_id, attempt_id, lock=True)
            if row.execution_mode != provider.mode:
                raise HTTPException(409, "Provider mode differs from original attempt")
            if row.status == "completed":
                return
            if (
                row.status.endswith("_running")
                and row.lease_until
                and row.lease_until > datetime.now(UTC)
            ):
                return
            if row.status.endswith("_failed") and not retry:
                return
            stage = "teaching" if row.medical_evaluation is not None else "medical"
            payload = row.snapshot["payload"]
            stage_payload = (
                payload if stage == "medical" else teaching_payload(payload, row.medical_evaluation)
            )
            row.status = stage + "_running"
            row.claim_token = token
            row.lease_until = datetime.now(UTC) + timedelta(seconds=timeout + 10)
            row.stage_error = None
        # No DB session/transaction remains open during provider execution.
        try:
            output, metadata = await asyncio.wait_for(
                provider.evaluate(stage, stage_payload, retry=retry), timeout=timeout
            )
            if stage == "medical":
                output = validate_output(
                    json.dumps(output, allow_nan=False), EvaluationRequest.model_validate(payload)
                )
            else:
                output = validate_teaching(stage_payload, output)
            json.dumps(metadata, allow_nan=False)
            error = None
        except TimeoutError:
            error = {"stage": stage, "code": "PROVIDER_TIMEOUT"}
        except Exception as exc:
            error = {
                "stage": stage,
                "code": exc.code if isinstance(exc, ServiceError) else "PROVIDER_OUTPUT_INVALID",
            }
        async with factory() as session, session.begin():
            row = await owned(session, user_id, attempt_id, lock=True)
            if row.claim_token != token:
                return  # Late response cannot overwrite a newly claimed retry.
            row.claim_token = None
            row.lease_until = None
            if error:
                row.status = stage + "_failed"
                row.stage_error = error
                return
            row.provider_metadata = {**row.provider_metadata, stage: metadata}
            if stage == "medical":
                row.medical_evaluation = output
                row.status = "pending"
            else:
                row.teaching_feedback = output
                row.status = "completed"
                return
