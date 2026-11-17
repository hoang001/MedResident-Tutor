"""Actual practice ASGI/router/service; actual PG rollback; actual retrieval. No production writes."""

import asyncio
import copy
import json
import sys
import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from . import ledger
from .common import ROOT, RUN, CORPUS, read, write, digest, file_hash


def practice_settings(base, live):
    update = {
        "practice_retrieval_strategy": "hybrid",
        "practice_retrieval_corpus": CORPUS,
        "practice_retrieval_encoder": ROOT
        / "data/local-models/embeddings/multilingual-e5-small",
    }
    if live:
        # Router.process and HTTPProvider must share the same local deadline.
        update.update(
            practice_runtime_profile="local", practice_local_medical_read_seconds=600
        )
    return base.model_copy(update=update)


async def recorded_medical_call(identifier, invoke):
    from app.modules.practice.contracts import ServiceError

    try:
        result = await invoke()
    except asyncio.CancelledError:
        ledger.finish(
            identifier,
            "failed",
            {"code": "PROVIDER_CANCELLED", "server_generation_may_finish": True},
        )
        raise
    except ServiceError as exc:
        ledger.finish(
            identifier, "failed", {"code": exc.code, "http_status": exc.status}
        )
        raise
    else:
        ledger.finish(identifier, "completed")
        return result


async def execute(context):
    from app.main import app
    from app.common.enums import QuestionType
    from app.core.config import get_settings
    from app.core.database import engine, SessionFactory
    from app.modules.practice import router as routes
    from app.modules.practice.models import PracticeAttempt
    from app.modules.practice.providers import HTTPProvider, MockProvider
    from app.modules.progress.models import LearningResult
    from app.modules.questions.models import Question, Rubric, RubricCriterion
    from app.modules.users.models import User
    from app.ai.retrieval.evidence import evidence_identities, verify_payload_evidence
    from app.ai.retrieval.factory import create_retriever

    live = context["phase"] == "live"
    original = (routes.SessionFactory, routes.provider, routes.get_settings)
    settings = practice_settings(get_settings(), live)
    development = read(RUN / "development-questions.json")
    medical = {r["question_id"]: r for r in read(RUN / "medical-development.json")}
    report = {
        "phase": context["phase"],
        "scope": "real practice ASGI/service + real PostgreSQL rollback + local semantic index",
        "teaching": "explicit mock; no Teaching model loaded",
        "browser_tested": False,
        "production_provider_modified": False,
        "cases": [],
        "controls": [],
        "model_attempts": 0,
    }
    attempt_ids = []
    chosen = (
        development
        if not live
        else [r for r in development if r["question_id"] in medical]
    )
    seeded = []
    baseline_learning = 0
    captured = []

    class Provider:
        mode = "http" if live else "mock"

        def __init__(self, config, sample):
            self.config = config
            self.sample = sample
            self.trace = None
            self.calls = {"medical": 0, "teaching": 0}
            self.mock = MockProvider()
            self.http = (
                HTTPProvider(
                    settings.model_copy(
                        update={
                            "medical_service_url": context["medical_url"],
                            "medical_service_api_key": context["medical_key"],
                        }
                    ),
                    stages=("medical",),
                )
                if live
                else None
            )

        def set_retrieval_context(self, trace):
            self.trace = trace
            if self.http:
                self.http.set_retrieval_context(trace)

        async def evaluate(self, stage, payload, retry=False):
            assert not retry, "No model retry permitted"
            self.calls[stage] += 1
            if stage == "teaching":
                value, meta = await self.mock.evaluate(stage, payload)
                return value, {**meta, "stage_execution": "explicit_teaching_mock"}
            verify_payload_evidence(payload, self.trace)
            captured.append(
                {
                    "trace_id": self.trace["trace_id"],
                    "payload": copy.deepcopy(payload),
                    "selected_evidence": copy.deepcopy(self.trace["selected_evidence"]),
                }
            )
            if not live:
                value, meta = await self.mock.evaluate(stage, payload)
                return value, {
                    **meta,
                    "stage_execution": "explicit_preflight_medical_mock",
                    "evidence_input_sha256": digest(
                        evidence_identities(payload["evidence"])
                    ),
                }
            planned = next(
                r
                for r in read(RUN / "planned-medical-payloads.json")
                if r["sample_id"] == self.sample
                and "retrieval_medical_" + r["mode"] + "_v1" == self.config
            )
            assert digest(payload) == planned["payload_sha256"], (
                "Runtime retrieval differs from the CPU-verified frozen payload"
            )
            fp = digest(
                {
                    "config": self.config,
                    "source_manifest": file_hash(CORPUS / "index-manifest.json"),
                    "payload": payload,
                    "model": read(ROOT / "data/local-models/locked-adapters.json")[
                        "medical"
                    ]["adapter_sha256"],
                    "prompt": file_hash(
                        ROOT / "model-training/src/medical/inference.py"
                    ),
                }
            )
            identifier = ledger.reserve(self.config, self.sample, fp)
            report["model_attempts"] += 1
            write(
                RUN / "requests" / (self.trace["trace_id"] + ".json"),
                {
                    "trace_id": self.trace["trace_id"],
                    "attempt_id": identifier,
                    "sample_id": self.sample,
                    "config": self.config,
                    "fingerprint": fp,
                    "payload_sha256": digest(payload),
                    "payload": payload,
                    "retrieval": self.trace,
                },
            )
            # Same HTTPProvider as the application; no transport/model retry.
            value, meta = await recorded_medical_call(
                identifier, lambda: self.http.evaluate(stage, payload)
            )
            return value, {
                **meta,
                "stage_execution": "real_medical_http",
                "shared_ledger_attempt_id": identifier,
            }

    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            factory = async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            routes.SessionFactory = factory
            routes.get_settings = lambda: settings
            async with factory() as session, session.begin():
                user = await session.scalar(
                    select(User).where(User.email == context["credentials"]["email"])
                )
                assert user is not None, "Existing review account missing"
                baseline_learning = await session.scalar(
                    select(func.count()).select_from(LearningResult)
                )
                for record in chosen:
                    qid = record["question_id"]
                    assert (
                        await session.scalar(
                            select(Question.id).where(Question.external_id == qid)
                        )
                        is None
                    )
                    q = Question(
                        external_id=qid,
                        content=record["question"],
                        question_type=QuestionType.SHORT_ANSWER,
                        created_by=user.id,
                        is_available=True,
                        bank_version=1,
                        import_metadata={
                            "dataset_fields": {"retrieval_scope": "textbook"}
                        },
                    )
                    session.add(q)
                    await session.flush()
                    spec = medical.get(qid)
                    rubric = (
                        spec["rubric"]
                        if spec
                        else {
                            "schema_version": "1.0.0",
                            "course_id": None,
                            "topic_id": None,
                            "scoring_rule": "routing preflight only, no semantic score reference",
                            "validation_status": "routing_test_only",
                            "expert_review_required": True,
                            "expert_review_reason": "No clinical scoring in preflight",
                            "max_score": 1.0,
                            "criteria": [
                                {
                                    "criterion_id": qid + "_ROUTE",
                                    "description": "Nội dung trong nguồn được hỏi.",
                                    "max_score": 1.0,
                                    "acceptable_variants": [],
                                    "common_incorrect_claims": [],
                                }
                            ],
                        }
                    )
                    r = Rubric(
                        external_id=qid + "_R1",
                        question_id=q.id,
                        name=qid + "_R1",
                        max_score=rubric["max_score"],
                        import_metadata={
                            "dataset_fields": {
                                k: v
                                for k, v in rubric.items()
                                if k
                                not in {
                                    "rubric_id",
                                    "question_id",
                                    "max_score",
                                    "criteria",
                                }
                            }
                        },
                    )
                    session.add(r)
                    await session.flush()
                    for i, c in enumerate(rubric["criteria"]):
                        session.add(
                            RubricCriterion(
                                external_id=c["criterion_id"],
                                rubric_id=r.id,
                                description=c["description"],
                                score=c["max_score"],
                                criterion_order=i + 1,
                                import_metadata={
                                    "dataset_fields": {
                                        "acceptable_variants": [],
                                        "common_incorrect_claims": [],
                                    }
                                },
                            )
                        )
                    seeded.append(qid)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://isolated-retrieval",
                timeout=None,
            ) as client:
                login = await client.post(
                    "/api/v1/auth/login", json=context["credentials"]
                )
                assert login.status_code == 200, "Existing review account login failed"
                client.headers["Authorization"] = (
                    "Bearer " + login.json()["access_token"]
                )

                def no_gold(obj):
                    if isinstance(obj, dict):
                        assert not set(obj) & {
                            "rubric",
                            "criteria",
                            "reference_answer",
                            "evidence",
                            "answer_annotations",
                        }
                        for v in obj.values():
                            no_gold(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            no_gold(v)

                for mode in ("vector", "hybrid"):
                    if report.get("stopped_after_medical_error"):
                        break
                    settings = settings.model_copy(
                        update={"practice_retrieval_strategy": mode}
                    )
                    for record in chosen:
                        if report.get("stopped_after_medical_error"):
                            break
                        qid = record["question_id"]
                        learner = await client.get("/api/v1/practice/questions/" + qid)
                        assert learner.status_code == 200, (
                            "New textbook question unavailable"
                        )
                        no_gold(learner.json())
                        answers = (
                            medical[qid]["answers"]
                            if live
                            else [
                                {
                                    "sample_id": qid + "__routing",
                                    "student_answer": "Synthetic routing answer only; Medical remains explicit mock.",
                                }
                            ]
                        )
                        for answer in answers:
                            provider = Provider(
                                "retrieval_medical_" + mode + "_v1", answer["sample_id"]
                            )
                            routes.provider = lambda: provider
                            key = str(uuid.uuid4())
                            body = {
                                "question_id": qid,
                                "student_answer": answer["student_answer"],
                            }
                            response = await client.post(
                                "/api/v1/practice/attempts",
                                headers={"Idempotency-Key": key},
                                json=body,
                            )
                            assert response.status_code == 200, (
                                "Practice submission HTTP failure"
                            )
                            result = response.json()
                            aid = uuid.UUID(result["id"])
                            attempt_ids.append(aid)
                            trace = result["retrieval"]
                            detail = await client.get(
                                "/api/v1/practice/attempts/" + result["id"]
                            )
                            assert detail.json() == result, (
                                "History detail changed saved evidence"
                            )
                            history = await client.get("/api/v1/practice/attempts")
                            assert any(
                                r["id"] == result["id"] and r["retrieval"] == trace
                                for r in history.json()
                            )
                            before = dict(provider.calls)
                            duplicate = await client.post(
                                "/api/v1/practice/attempts",
                                headers={"Idempotency-Key": key},
                                json=body,
                            )
                            assert (
                                duplicate.json()["id"] == result["id"]
                                and before == provider.calls
                            )
                            row = {
                                "sample_id": answer["sample_id"],
                                "mode": mode,
                                "http_status": response.status_code,
                                "attempt": result,
                                "provider_calls": provider.calls,
                                "learner_api_no_gold": True,
                                "history_snapshot_matches": True,
                                "idempotent_no_second_call": True,
                            }
                            if live:
                                row["expected_vector"] = answer["expected_vector"]
                            report["cases"].append(row)
                            if live and result["status"] == "medical_failed":
                                # A timed-out HTTP request can leave the model busy.
                                # Preserve this attempt and stop instead of spending
                                # subsequent sample slots on a cascade of HTTP 429s.
                                report["stopped_after_medical_error"] = {
                                    "sample_id": answer["sample_id"],
                                    "mode": mode,
                                    "stage_error": result.get("stage_error"),
                                }
                                break
                if not live:
                    # Actual corpus/query plus an unavailable Neo4j endpoint, not a fake successful KG.
                    config = settings.model_copy(
                        update={"neo4j_uri": "bolt://host.docker.internal:1"}
                    )
                    r = create_retriever(config)
                    try:
                        fallback = await r.retrieve(
                            chosen[0]["question_id"],
                            chosen[0]["question"],
                            str(uuid.uuid4()),
                        )
                        assert (
                            fallback.trace["effective_strategy"] == "vector"
                            and not fallback.trace["kg_contributed"]
                        )
                        report["controls"].append(
                            {
                                "name": "actual_neo4j_connection_failure",
                                "trace": fallback.trace,
                            }
                        )
                    finally:
                        await r.graph.close()
                    # Unmapped natural off-topic query. Record its actual outcome, never force it empty.
                    r = create_retriever(settings)
                    try:
                        none = await r.retrieve(
                            "UNMAPPED_DEV",
                            "Lịch thi đấu bóng đá World Cup trên sao Hỏa?",
                            str(uuid.uuid4()),
                        )
                        assert (
                            not none.evidence
                            and none.trace["status"] == "insufficient_evidence"
                        )
                        report["controls"].append(
                            {"name": "off_topic_no_mapping", "trace": none.trace}
                        )
                        scoped = await r.retrieve(
                            "UNMAPPED_BOOK_DEV",
                            chosen[0]["question"],
                            str(uuid.uuid4()),
                            source_ids=[chosen[0]["source_id"]],
                        )
                        assert (
                            scoped.trace["effective_strategy"] == "vector"
                            and scoped.evidence
                        )
                        report["controls"].append(
                            {
                                "name": "unmapped_verified_book_vector_fallback",
                                "trace": scoped.trace,
                            }
                        )
                    finally:
                        await r.graph.close()
                    # Same source index; explicit offline graph path must retain its own label.
                    r = create_retriever(
                        settings.model_copy(
                            update={"practice_retrieval_graph": "offline"}
                        )
                    )
                    try:
                        offline = await r.retrieve(
                            chosen[0]["question_id"],
                            chosen[0]["question"],
                            str(uuid.uuid4()),
                        )
                        assert (
                            offline.trace["kg_data_source"] == "offline_graph_snapshot"
                        )
                        report["controls"].append(
                            {"name": "offline_snapshot_label", "trace": offline.trace}
                        )
                    finally:
                        await r.graph.close()
                    # External clinical cases are deliberately prelinked under hybrid configuration.
                    for qid in ("CLINICAL_DEMO_V1_CASE01", "CLINICAL_DEMO_V1_XR01"):
                        provider = Provider("not_model", qid)
                        routes.provider = lambda: provider
                        learner = await client.get("/api/v1/practice/questions/" + qid)
                        assert learner.status_code == 200
                        no_gold(learner.json())
                        response = await client.post(
                            "/api/v1/practice/attempts",
                            headers={"Idempotency-Key": str(uuid.uuid4())},
                            json={
                                "question_id": qid,
                                "student_answer": "Synthetic no-model routing check.",
                            },
                        )
                        assert response.status_code == 200
                        result = response.json()
                        attempt_ids.append(uuid.UUID(result["id"]))
                        assert (
                            result["retrieval"]["effective_strategy"] == "prelinked"
                            and result["retrieval"]["neo4j_queries"] == 0
                        )
                        report["controls"].append(
                            {
                                "name": qid + "_stays_prelinked",
                                "trace": result["retrieval"],
                            }
                        )
                    # Real API failure: book-like scope without a verified source mapping.
                    async with factory() as session, session.begin():
                        qid = "KGR_DEV_UNSCOPED_NEGATIVE"
                        q = Question(
                            external_id=qid,
                            content="Lịch thi đấu bóng đá World Cup trên sao Hỏa?",
                            question_type=QuestionType.SHORT_ANSWER,
                            created_by=user.id,
                            is_available=True,
                            import_metadata={
                                "dataset_fields": {"retrieval_scope": "textbook"}
                            },
                        )
                        session.add(q)
                        await session.flush()
                        template = await session.scalar(
                            select(Rubric).where(
                                Rubric.external_id == chosen[0]["question_id"] + "_R1"
                            )
                        )
                        r = Rubric(
                            external_id=qid + "_R1",
                            question_id=q.id,
                            name=qid,
                            max_score=1.0,
                            import_metadata=copy.deepcopy(template.import_metadata),
                        )
                        session.add(r)
                        await session.flush()
                        session.add(
                            RubricCriterion(
                                external_id=qid + "_C1",
                                rubric_id=r.id,
                                description="Routing negative control only",
                                score=1.0,
                                criterion_order=1,
                                import_metadata={
                                    "dataset_fields": {
                                        "acceptable_variants": [],
                                        "common_incorrect_claims": [],
                                    }
                                },
                            )
                        )
                        seeded.append(qid)
                    provider = Provider("not_model", qid)
                    routes.provider = lambda: provider
                    response = await client.post(
                        "/api/v1/practice/attempts",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json={
                            "question_id": qid,
                            "student_answer": "No medical claim.",
                        },
                    )
                    assert response.status_code == 200
                    result = response.json()
                    attempt_ids.append(uuid.UUID(result["id"]))
                    assert (
                        result["stage_error"]["code"]
                        == "RETRIEVAL_INSUFFICIENT_EVIDENCE"
                    )
                    assert provider.calls == {"medical": 0, "teaching": 0}
                    report["controls"].append(
                        {
                            "name": "api_insufficient_evidence_no_provider",
                            "trace": result["retrieval"],
                            "stage_error": result["stage_error"],
                            "provider_calls": provider.calls,
                        }
                    )
            async with factory() as session:
                assert (
                    await session.scalar(
                        select(func.count()).select_from(LearningResult)
                    )
                    == baseline_learning
                )
                for row in captured:
                    assert (
                        evidence_identities(row["payload"]["evidence"])
                        == row["selected_evidence"]
                    )
            report["payload_captures"] = captured
        finally:
            routes.SessionFactory, routes.provider, routes.get_settings = original
            await outer.rollback()
            report["outer_transaction_rolled_back"] = True
    async with SessionFactory() as session:
        assert not (
            await session.scalars(
                select(PracticeAttempt.id).where(PracticeAttempt.id.in_(attempt_ids))
            )
        ).all()
        assert not (
            await session.scalars(
                select(Question.id).where(Question.external_id.in_(seeded))
            )
        ).all()
        assert (
            await session.scalar(select(func.count()).select_from(LearningResult))
            == baseline_learning
        )
    report["test_attempts_and_questions_absent_after_rollback"] = True
    report["mastery_unchanged"] = True
    await engine.dispose()
    return report


def main():
    context = json.loads(sys.stdin.read())
    try:
        report = asyncio.run(execute(context))
    except Exception as exc:
        # Do not serialize stack/context/DB URL/keys or HTTP headers.
        report = {
            "phase": context.get("phase"),
            "status": "failed",
            "error_type": type(exc).__name__,
        }
        message = str(exc)
        if isinstance(exc, AssertionError) and not any(
            s in message for s in ("postgresql", "://", "password", "Bearer")
        ):
            report["assertion"] = message[:200]
    print("RETRIEVAL_INTEGRATION_REPORT=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
