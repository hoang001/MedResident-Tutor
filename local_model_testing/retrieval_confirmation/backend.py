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
from .state import can_continue


def stub_worker():
    return {
        "loaded": True,
        "idle": True,
        "execution": "explicit_no_model_contract_stub",
    }


async def worker_status(context):
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            context["medical_url"] + "/experiment/state",
            headers={"X-API-Key": context["medical_key"]},
        )
        response.raise_for_status()
        return response.json()


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

    live = context["phase"] == "live"
    original = (
        routes.SessionFactory,
        routes.provider,
        routes.get_settings,
        routes.process,
    )
    settings = practice_settings(get_settings(), True)
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
        "effective_runtime": {
            "fastapi_app": app.title,
            "caller_transport_timeout": None,
            "local_profile": settings.practice_runtime_profile,
            "http_clients": [],
            "service_deadlines": [],
            "concurrency": 1,
        },
    }
    real_process = routes.process

    async def observed_process(*args, **kwargs):
        deadline = args[4]
        value = deadline("medical") if callable(deadline) else deadline
        report["effective_runtime"]["service_deadlines"].append(value)
        assert value == 625, "Practice orchestration did not receive the local profile"
        return await real_process(*args, **kwargs)

    routes.process = observed_process
    attempt_ids = []
    chosen = [r for r in development if r["question_id"] in medical]
    seeded = []
    baseline_learning = 0
    captured = []

    class Provider:
        mode = "http"

        def __init__(self, config, sample):
            self.config = config
            self.sample = sample
            self.trace = None
            self.calls = {"medical": 0, "teaching": 0}
            self.mock = MockProvider()
            self.http = HTTPProvider(
                settings.model_copy(
                    update={
                        "medical_service_url": context.get(
                            "medical_url", "http://explicit-contract-stub"
                        ),
                        "medical_service_api_key": context.get(
                            "medical_key", "test-fixture"
                        ),
                    }
                ),
                stages=("medical",),
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

            async def transport():
                original_client = httpx.AsyncClient

                async def handler(request):
                    received = json.loads(request.content)
                    verify_payload_evidence(received, self.trace)
                    value, _ = await self.mock.evaluate(stage, received)
                    return httpx.Response(
                        200,
                        json={
                            "medical_evaluation": value,
                            "model_metadata": {
                                "execution": "explicit_no_model_contract_stub"
                            },
                            "timing": {},
                        },
                    )

                def observed_client(*args, **kwargs):
                    actual = kwargs["timeout"].as_dict()
                    report["effective_runtime"]["http_clients"].append(actual)
                    assert actual["read"] == 600
                    assert self.http.settings.practice_stage_deadline("medical") == 625
                    if not live:
                        kwargs["transport"] = httpx.MockTransport(handler)
                    return original_client(*args, **kwargs)

                httpx.AsyncClient = observed_client
                try:
                    return await self.http.evaluate(stage, payload)
                finally:
                    httpx.AsyncClient = original_client

            if not live:
                value, meta = await transport()
                return value, {
                    **meta,
                    "stage_execution": "explicit_http_contract_stub_no_model",
                }
            planned = next(
                r
                for r in read(RUN / "planned-medical-payloads.json")
                if r["sample_id"] == self.sample
                and "retrieval_medical_" + r["mode"] + "_v2" == self.config
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
            value, meta = await recorded_medical_call(identifier, transport)
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
                routes.provider = lambda: Provider(
                    "configuration_probe", "no_inference"
                )
                login = await client.post(
                    "/api/v1/auth/login", json=context["credentials"]
                )
                assert login.status_code == 200, "Existing review account login failed"
                client.headers["Authorization"] = (
                    "Bearer " + login.json()["access_token"]
                )
                effective_config = (await client.get("/api/v1/practice/config")).json()
                assert effective_config["request_timeout_ms"] == 665000
                report["effective_runtime"]["fastapi_config_endpoint"] = (
                    effective_config
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

                schedule = [
                    (record, answer, mode)
                    for record in chosen
                    for answer in medical[record["question_id"]]["answers"]
                    for mode in ("vector", "hybrid")
                ]
                for record, answer, mode in schedule:
                    settings = settings.model_copy(
                        update={"practice_retrieval_strategy": mode}
                    )
                    qid = record["question_id"]
                    learner = await client.get("/api/v1/practice/questions/" + qid)
                    assert learner.status_code == 200, (
                        "New textbook question unavailable"
                    )
                    no_gold(learner.json())
                    before_worker = (
                        await worker_status(context) if live else stub_worker()
                    )
                    assert before_worker["loaded"] and before_worker["idle"], (
                        "WORKER_NOT_IDLE_NO_REQUEST_SENT"
                    )
                    provider = Provider(
                        "retrieval_medical_" + mode + "_v2", answer["sample_id"]
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
                    row["worker_before"] = before_worker
                    row["worker_after"] = (
                        await worker_status(context) if live else stub_worker()
                    )
                    assert (
                        (trace["neo4j_queries"] == 0 and not trace["kg_contributed"])
                        if mode == "vector"
                        else trace["kg_contributed"]
                    )
                    if mode == "vector":
                        assert all(
                            r["semantic_score"] == r["combined_score"]
                            for r in trace["ranking"]
                        )
                    report["cases"].append(row)
                    write(RUN / (context["phase"] + "-partial.json"), report)
                    if live and not can_continue(result, row["worker_after"]):
                        report["stopped_after_medical_error"] = {
                            "sample_id": answer["sample_id"],
                            "mode": mode,
                            "stage_error": result.get("stage_error"),
                        }
                        break
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
            (
                routes.SessionFactory,
                routes.provider,
                routes.get_settings,
                routes.process,
            ) = original
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
