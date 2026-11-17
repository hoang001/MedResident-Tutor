"""Fresh BE child app against a source snapshot, real Medical HTTP, mock Teaching.

Receives secrets on stdin only. All DB changes are rolled back. No model retry.
"""

import asyncio
import json
import os
import sys
import time
import uuid


async def execute(context):
    sys.path.insert(0, context["backend_source"])
    from app.main import app
    from app.core.config import Settings
    from app.core.database import engine, SessionFactory
    from app.modules.practice import router as routes
    from app.modules.practice.models import PracticeAttempt
    from app.modules.practice.providers import HTTPProvider, MockProvider
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy import select
    import httpx

    updates = {k.lower(): v for k, v in context["profile"]["backend_env"].items()}
    settings = Settings(
        _env_file=None,
        **updates,
        medical_service_url=context["medical_url"],
        medical_service_api_key=context["medical_key"],
    )
    assert (
        settings.app_env == "development"
        and settings.practice_runtime_profile == "local"
    )
    original = (routes.SessionFactory, routes.provider, routes.get_settings)
    report = {
        "scope": "Fresh source BE ASGI child + real Medical HTTP + explicit Teaching mock; PostgreSQL rollback",
        "profile": {
            "name": settings.practice_runtime_profile,
            "medical_transport": settings.practice_transport_timeouts("medical"),
            "medical_outer_seconds": settings.practice_stage_deadline("medical"),
            "teaching_outer_seconds": settings.practice_stage_deadline("teaching"),
            "frontend_request_ms": settings.practice_request_timeout_ms(),
        },
        "cases": [],
        "browser_e2e": False,
        "mastery_updated": False,
        "automatic_retries": 0,
    }
    ids = []

    class Mixed:
        mode = "http"

        def __init__(self, rid):
            self.http = HTTPProvider(settings, stages=("medical",), request_id=rid)
            self.mock = MockProvider()
            self.calls = {"medical": 0, "teaching": 0}

        async def evaluate(self, stage, payload, retry=False):
            assert not retry
            self.calls[stage] += 1
            if stage == "medical":
                value, metadata = await self.http.evaluate(stage, payload)
                return value, {
                    **metadata,
                    "stage_execution": "local_medical_real_http",
                    "profile": "local",
                }
            value, metadata = await self.mock.evaluate(stage, payload)
            return value, {**metadata, "stage_execution": "explicit_teaching_mock"}

    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            routes.SessionFactory = async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            routes.get_settings = lambda: settings
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://isolated-local-profile",
                timeout=settings.practice_request_timeout_ms() / 1000 + 5,
            ) as client:
                login = await client.post(
                    "/api/v1/auth/login", json=context["credentials"]
                )
                assert login.status_code == 200, "Review account login failed"
                client.headers["Authorization"] = (
                    "Bearer " + login.json()["access_token"]
                )
                for case in context["cases"]:
                    rid = str(uuid.uuid4())
                    provider = Mixed(rid)
                    routes.provider = lambda: provider
                    cfg = await client.get("/api/v1/practice/config")
                    assert cfg.json()["request_timeout_ms"] == 155000
                    key = uuid.uuid4().hex
                    payload = {
                        "question_id": case["question_id"],
                        "student_answer": case["student_answer"],
                    }
                    started = time.perf_counter()
                    async with asyncio.timeout(
                        settings.practice_request_timeout_ms() / 1000 + 5
                    ):
                        response = await client.post(
                            "/api/v1/practice/attempts",
                            json=payload,
                            headers={"Idempotency-Key": key, "X-Request-ID": rid},
                        )
                    row = {
                        "case_id": case["case_id"],
                        "request_id": rid,
                        "http_status": response.status_code,
                        "wall_seconds": time.perf_counter() - started,
                        "provider_calls": dict(provider.calls),
                    }
                    if response.status_code == 200:
                        result = response.json()
                        ids.append(uuid.UUID(result["id"]))
                        row["attempt"] = result
                        detail = await client.get(
                            "/api/v1/practice/attempts/" + result["id"]
                        )
                        history = await client.get("/api/v1/practice/attempts")
                        row["detail_reload_matches"] = detail.json() == result
                        row["history_contains_attempt"] = any(
                            a["id"] == result["id"] for a in history.json()
                        )
                        if result["status"] == "completed":
                            assert result["execution_mode"] == "http"
                            assert (
                                result["provider_metadata"]["medical"][
                                    "stage_execution"
                                ]
                                == "local_medical_real_http"
                            )
                            assert (
                                result["provider_metadata"]["teaching"][
                                    "stage_execution"
                                ]
                                == "explicit_teaching_mock"
                            )
                            before = dict(provider.calls)
                            duplicate = await client.post(
                                "/api/v1/practice/attempts",
                                json=payload,
                                headers={"Idempotency-Key": key},
                            )
                            row["duplicate_same_attempt_no_model_call"] = (
                                duplicate.json()["id"] == result["id"]
                                and provider.calls == before
                            )
                            assert row["duplicate_same_attempt_no_model_call"]
                    else:
                        row["api_error"] = response.json()
                    report["cases"].append(row)
        finally:
            routes.SessionFactory, routes.provider, routes.get_settings = original
            await transaction.rollback()
            report["outer_transaction_rolled_back"] = True
    async with SessionFactory() as session:
        remaining = (
            await session.scalars(
                select(PracticeAttempt.id).where(PracticeAttempt.id.in_(ids))
            )
        ).all()
        assert not remaining
        report["all_test_attempts_absent_after_rollback"] = True
    await engine.dispose()
    return report


if __name__ == "__main__":
    context = json.loads(sys.stdin.read())
    try:
        report = asyncio.run(execute(context))
    except Exception as exc:
        message = str(exc)
        for secret in (
            context.get("medical_key"),
            context.get("credentials", {}).get("password"),
            os.environ.get("DATABASE_URL"),
            os.environ.get("JWT_SECRET_KEY"),
        ):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        report = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": message,
        }
    print("LOCAL_PROFILE_REPORT=" + json.dumps(report, ensure_ascii=False))
