import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.ai.retrieval.evidence import prelinked_trace, unavailable_bundle, verify_payload_evidence
from app.integration.reader import medical_payload, question_rubric
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.practice.assets import authored_metadata, learner_view, solution_view
from app.modules.practice.contracts import (
    EvaluationRequest,
    ServiceError,
    validate_output,
    validate_teaching,
)
from app.modules.practice.models import PracticeAttempt
from app.modules.practice.structured import definition, grade
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
    structured = getattr(row, "structured_result", None)
    evaluated = row.medical_evaluation is not None or structured is not None
    result = {
        "id": str(row.id),
        "question_id": row.snapshot["payload"]["rubric"]["question_id"],
        "question": row.snapshot["payload"]["question"],
        "student_answer": row.student_answer,
        "status": row.status,
        "execution_mode": row.execution_mode,
        "medical_evaluation": row.medical_evaluation,
        "teaching_feedback": row.teaching_feedback,
        "evidence": row.snapshot["payload"]["evidence"] if evaluated else [],
        "provenance": row.snapshot["provenance"] if evaluated else [],
        "snapshot_hash": row.snapshot["hash"],
        "provider_metadata": row.provider_metadata,
        "stage_error": row.stage_error,
        "created_at": row.created_at.isoformat(),
    }
    if structured is not None:
        result["structured_result"] = structured
        result["question_version"] = row.snapshot["question_version"]
    if "retrieval" in row.snapshot:
        result["retrieval"] = row.snapshot["retrieval"]
    if evaluated and "approved_package" in row.snapshot:
        result["reference_answer"] = row.snapshot["approved_package"]["reference_answer"]
        result["question_version"] = row.snapshot["question_version"]
    authored = row.snapshot.get("clinical_exercise")
    if authored:
        result["clinical_exercise"] = learner_view(authored, "/practice/attempts/" + str(row.id))
        if structured is not None:
            result["clinical_exercise"] = learner_view(
                authored, "/practice/attempts/" + str(row.id), structured=True
            )
            result["question"] = (
                authored["learner"]["presentation"]
                + "\n\n"
                + "\n".join(part["label"] for part in structured["parts"])
            )
        if evaluated:
            result["clinical_solution"] = solution_view(authored)
    return result


async def submit(
    factory,
    user_id,
    question_external_id,
    answer,
    key,
    provider,
    *,
    structured_answers=None,
    revision_id=None,
    retrieval_settings=None,
    retriever=None,
):
    request = {"question_id": question_external_id, "student_answer": answer}
    if structured_answers is not None or revision_id is not None:
        request.update(structured_answers=structured_answers, revision_id=revision_id)
    input_hash = digest(request)
    async with factory() as session, session.begin():
        # Serialize this user's exact submission key, including requests for different
        # questions. A concurrent replay must find the saved result before grading again.
        lock_id = int.from_bytes(
            hashlib.sha256(f"practice:{user_id}:{key}".encode()).digest()[:8], signed=True
        )
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
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
        exercise = definition(question.import_metadata)
        attempt_id = uuid.uuid4()
        from app.ai.retrieval.factory import create_retriever, is_textbook_question
        from app.core.config import get_settings

        settings = retrieval_settings or get_settings()
        strategy = settings.practice_retrieval_strategy
        approved = (question.import_metadata or {}).get("approved_package")
        use_retrieval = (
            not approved
            and not exercise
            and strategy != "prelinked"
            and is_textbook_question(question, settings)
        )
        retrieval_trace = None
        dynamic_provenance = None
        structured_result = None
        if exercise:
            if revision_id != exercise.revision_id or structured_answers is None or answer:
                raise HTTPException(422, "Send revision_id and structured_answers; no essay field")
            structured_result = grade(exercise, structured_answers)
            # Reuse source/rubric assembly only. This is never sent to a provider.
            payload = await medical_payload(session, question_external_id, "Snapshot assembly")
            payload.pop("student_answer")
            mode = "structured"
        else:
            if structured_answers is not None or revision_id is not None:
                raise HTTPException(422, "This question accepts an essay only")
            if not isinstance(answer, str) or not answer.strip():
                raise HTTPException(422, "Student answer is empty")
            provider = provider() if callable(provider) else provider
            mode = provider.mode
            if approved:
                from app.modules.questions.authoring import approved_payload

                payload, package = approved_payload(question, answer)
                dynamic_provenance = package["provenance"]
                retrieval_trace = prelinked_trace(
                    payload["evidence"], str(attempt_id), "approved_package"
                )
                retrieval_trace.update(
                    effective_strategy="approved_package",
                    data_source="postgresql_approved_package",
                    package_sha256=approved["sha256"],
                    revision_id=package["revision_id"],
                    adequacy="admin_accepted_not_expert_verified",
                )
            elif (question.import_metadata or {}).get("origin") == "admin_ui":
                raise HTTPException(422, "Published admin question has no approved package")
            elif use_retrieval:
                # No rubric links/gold evidence are read on this path. The retriever's
                # signature accepts only question identity/text, never the student answer.
                payload = await question_rubric(session, question_external_id, answer)
                active = None
                try:
                    active = retriever or await asyncio.to_thread(create_retriever, settings)
                    source_scope = (
                        (question.import_metadata or {})
                        .get("dataset_fields", {})
                        .get("source_ids", [])
                    )
                    bundle = await active.retrieve(
                        question_external_id,
                        payload["question"],
                        str(attempt_id),
                        source_ids=source_scope,
                    )
                except (OSError, ImportError, ValueError, KeyError) as exc:
                    bundle = unavailable_bundle(
                        question_external_id, str(attempt_id), strategy, type(exc).__name__
                    )
                finally:
                    if retriever is None and active is not None:
                        await active.graph.close()
                payload["evidence"] = bundle.evidence
                retrieval_trace = bundle.trace
                dynamic_provenance = bundle.provenance
                verify_payload_evidence(payload, retrieval_trace)
            else:
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
        if dynamic_provenance is not None:
            provenance = dynamic_provenance
        if retrieval_trace is None:
            reason = (
                "structured_grader_no_model"
                if exercise
                else "external_case_or_unmapped_source_scope"
                if strategy != "prelinked"
                else None
            )
            retrieval_trace = prelinked_trace(
                payload["evidence"], str(attempt_id), strategy, reason
            )
        snapshot = {"payload": payload, "provenance": provenance}
        snapshot["retrieval"] = retrieval_trace
        if mode == "http":
            # Freeze only this learner's completed real-provider history. Retries use
            # the same context; mock/structured scores never become model context.
            snapshot["learner_context"] = await learner_context(session, user_id)
        if approved:
            snapshot["approved_package"] = {k: v for k, v in approved.items() if k != "payload"}
            snapshot["question_version"] = approved["question_version"]
        if exercise:
            snapshot.update(
                structured_exercise=exercise.model_dump(),
                structured_answers=structured_answers,
                question_version=question.bank_version,
            )
        authored = authored_metadata(question.import_metadata)
        if authored:
            # Outside the locked four-field Medical contract, retained for historical assets.
            snapshot["clinical_exercise"] = authored
        snapshot["hash"] = digest(snapshot)
        result = await session.execute(
            insert(PracticeAttempt)
            .values(
                id=attempt_id,
                user_id=user_id,
                question_id=question.id,
                idempotency_key=key,
                input_hash=input_hash,
                student_answer=answer or "",
                status="completed" if exercise else "pending",
                execution_mode=mode,
                snapshot=snapshot,
                structured_result=structured_result,
                provider_metadata=(
                    {
                        "grader": "deterministic-v1",
                        "feedback": "authored-source-linked-v1",
                        "model_calls": 0,
                    }
                    if exercise
                    else {}
                ),
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


async def learner_context(session, user_id):
    recent = (
        await session.scalars(
            select(PracticeAttempt)
            .where(
                PracticeAttempt.user_id == user_id,
                PracticeAttempt.execution_mode == "http",
                PracticeAttempt.status == "completed",
                PracticeAttempt.medical_evaluation.is_not(None),
            )
            .order_by(PracticeAttempt.created_at.desc(), PracticeAttempt.id.desc())
            .limit(5)
        )
    ).all()
    # Counts are observed history, not inferred mastery or new clinical claims.
    summary = [
        {
            "correct_points_count": len(r.medical_evaluation.get("correct_points", [])),
            "incorrect_points_count": len(r.medical_evaluation.get("incorrect_points", [])),
            "missing_points_count": len(r.medical_evaluation.get("missing_points", [])),
        }
        for r in recent
    ]
    return {
        "mastery": [],
        "recurring_errors": [],
        "recent_improvements": [],
        "recent_attempts_summary": (
            "Prior completed real-provider practice (newest first; counts only, not mastery): "
            + json.dumps(summary, separators=(",", ":"))
            if summary
            else None
        ),
    }


def teaching_payload(payload, medical, context=None):
    # No mastery is inferred; taxonomy remains explicitly unverified.
    return {
        "schema_version": "1.0.0",
        "question": payload["question"],
        "student_answer": payload["student_answer"],
        "medical_evaluation": medical,
        "learner_context": context
        if context is not None
        else {
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
            if row.execution_mode == "structured":
                return
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
            trace = row.snapshot.get("retrieval")
            if stage == "medical" and trace:
                try:
                    verify_payload_evidence(row.snapshot["payload"], trace)
                    if trace["status"] == "insufficient_evidence":
                        raise ValueError(
                            trace.get("failure_code", "RETRIEVAL_INSUFFICIENT_EVIDENCE")
                        )
                except ValueError as exc:
                    row.status = "medical_failed"
                    row.stage_error = {"stage": "retrieval", "code": str(exc)}
                    return
            stage_timeout = timeout(stage) if callable(timeout) else timeout
            payload = row.snapshot["payload"]
            stage_payload = (
                payload
                if stage == "medical"
                else teaching_payload(
                    payload, row.medical_evaluation, row.snapshot.get("learner_context")
                )
            )
            row.status = stage + "_running"
            row.claim_token = token
            row.lease_until = datetime.now(UTC) + timedelta(seconds=stage_timeout + 10)
            row.stage_error = None
        # No DB session/transaction remains open during provider execution.
        try:
            started = asyncio.get_running_loop().time()
            if stage == "medical" and trace and hasattr(provider, "set_retrieval_context"):
                provider.set_retrieval_context(trace)
            output, metadata = await asyncio.wait_for(
                provider.evaluate(stage, stage_payload, retry=retry), timeout=stage_timeout
            )
            # wait_for can return a late value if a provider suppresses cancellation.
            if asyncio.get_running_loop().time() - started >= stage_timeout:
                raise TimeoutError
            if stage == "medical":
                output = validate_output(
                    json.dumps(output, allow_nan=False), EvaluationRequest.model_validate(payload)
                )
            else:
                output = validate_teaching(stage_payload, output)
            json.dumps(metadata, allow_nan=False)
            error = None
        except TimeoutError:
            error = {
                "stage": stage,
                "code": "MODEL_SERVICE_TIMEOUT"
                if getattr(provider, "client", None)
                else "PROVIDER_TIMEOUT",
            }
        except Exception as exc:
            error = {
                "stage": stage,
                "code": exc.code if isinstance(exc, ServiceError) else "PROVIDER_OUTPUT_INVALID",
            }
            if getattr(exc, "upstream_status", None) is not None:
                error["upstream_http_status"] = exc.upstream_status
            if getattr(exc, "upstream_code", None):
                error["upstream_code"] = exc.upstream_code
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
