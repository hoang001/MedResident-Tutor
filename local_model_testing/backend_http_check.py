"""Executed in an isolated child of the existing BE container; stdin carries auth.

Real FastAPI practice/auth/snapshot/validators and local Medical HTTP. Teaching is
explicit mock. All practice writes are enclosed in a rolled-back outer transaction.
The BE process serving port 8000 and its provider settings are never changed.
"""

import asyncio
import json
import sys
import uuid
import os
import re
import copy

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import app
from app.core.database import engine, SessionFactory
from app.modules.practice import router as practice_router
from app.modules.practice.models import PracticeAttempt
from app.modules.practice.providers import MockProvider
from app.modules.practice.contracts import ServiceError


class MixedProvider:
    mode = "http"

    def __init__(self, context):
        self.context = context
        self.mock = MockProvider()
        self.calls = {"medical": 0, "teaching": 0}

    async def evaluate(self, stage, payload, retry=False):
        if retry:
            raise RuntimeError("No automatic retries permitted")
        self.calls[stage] += 1
        if self.context.get("replay"):
            saved = self.context["replay"]
            expected = copy.deepcopy(saved[stage + "_input"])
            incoming = copy.deepcopy(payload)
            if stage == "teaching":
                expected["metadata"].pop("question_id", None)
            assert incoming == expected, "Replay input differs from recorded model task"
            return copy.deepcopy(saved[stage + "_output"]), {
                "execution_mode": "replay",
                "stage_execution": "replay_saved_local_" + stage,
                "source_sha256": saved[stage + "_source_sha256"],
                "new_model_call": False,
                "input_comparison": "JSON equality; saved Teaching metadata tracking question_id excluded",
            }
        if stage == "teaching":
            value, metadata = await self.mock.evaluate(stage, payload)
            return value, {
                **metadata,
                "stage_execution": "explicit_teaching_mock",
                "integration_test": True,
            }
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10)) as client:
            response = await client.post(
                self.context["medical_url"] + "/medical/evaluate",
                json=payload,
                headers={"X-API-Key": self.context["medical_key"]},
            )
        if response.status_code != 200:
            try:
                code = (
                    response.json().get("error", {}).get("code", "MEDICAL_HTTP_ERROR")
                )
            except ValueError:
                code = "MEDICAL_HTTP_ERROR"
            raise ServiceError(code, response.status_code)
        data = response.json()
        return data["medical_evaluation"], {
            "execution_mode": "http",
            "stage_execution": "local_medical_real_http",
            "model_metadata": data["model_metadata"],
            "timing": data.get("timing", {}),
        }


async def check(context):
    provider = MixedProvider(context)
    original_factory, original_provider = (
        practice_router.SessionFactory,
        practice_router.provider,
    )
    attempt_id = None
    report = {
        "scope": "Real BE ASGI app + real PostgreSQL transaction + real Medical HTTP; Teaching explicit mock",
        "browser_FE_tested": False,
        "port_8000_provider_modified": False,
        "automatic_retries": 0,
        "mastery_updated": False,
    }
    if context.get("replay"):
        report["scope"] = (
            "Real BE ASGI app/PostgreSQL rollback, replay of both saved local model outputs; no live model service"
        )
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            practice_router.SessionFactory = async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            practice_router.provider = lambda: provider
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://isolated-local-practice",
            ) as client:
                login = await client.post(
                    "/api/v1/auth/login", json=context["credentials"]
                )
                assert login.status_code == 200, "Existing review account login failed"
                client.headers["Authorization"] = (
                    "Bearer " + login.json()["access_token"]
                )
                response = await client.post(
                    "/api/v1/practice/attempts",
                    headers={"Idempotency-Key": uuid.uuid4().hex},
                    json={
                        "question_id": context["question_id"],
                        "student_answer": context["student_answer"],
                    },
                )
                report["submit_http"] = response.status_code
                assert response.status_code == 200, "Practice request failed"
                result = response.json()
                attempt_id = uuid.UUID(result["id"])
                report["attempt"] = result
                history = await client.get("/api/v1/practice/attempts/" + result["id"])
                report["history_reload_http"] = history.status_code
                report["history_reload_matches"] = (
                    history.json().get("medical_evaluation")
                    == result["medical_evaluation"]
                )
                report["provider_calls"] = provider.calls
                report["completed"] = result["status"] == "completed"
                assert result["execution_mode"] == "http"
                if result["status"] == "completed":
                    medical_execution = (
                        "replay_saved_local_medical"
                        if context.get("replay")
                        else "local_medical_real_http"
                    )
                    teaching_execution = (
                        "replay_saved_local_teaching"
                        if context.get("replay")
                        else "explicit_teaching_mock"
                    )
                    assert (
                        result["provider_metadata"]["medical"]["stage_execution"]
                        == medical_execution
                    )
                    assert (
                        result["provider_metadata"]["teaching"]["stage_execution"]
                        == teaching_execution
                    )
        finally:
            practice_router.SessionFactory, practice_router.provider = (
                original_factory,
                original_provider,
            )
            await outer.rollback()
    report["outer_transaction_rolled_back"] = True
    if attempt_id:
        async with SessionFactory() as session:
            assert (
                await session.scalar(
                    select(PracticeAttempt.id).where(PracticeAttempt.id == attempt_id)
                )
                is None
            )
        report["test_attempt_absent_after_rollback"] = True
    await engine.dispose()
    return report


if __name__ == "__main__":
    context = {}
    try:
        context = json.loads(sys.stdin.read())
        print(
            "LOCAL_HTTP_REPORT="
            + json.dumps(asyncio.run(check(context)), ensure_ascii=False)
        )
    except Exception as exc:
        # No credentials, connection strings or request bodies in diagnostics.
        message = str(exc)
        for secret in (
            context.get("medical_key"),
            context.get("credentials", {}).get("password"),
            os.environ.get("DATABASE_URL"),
        ):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        message = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", message)
        print(
            "LOCAL_HTTP_REPORT="
            + json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": message,
                }
            )
        )
        raise SystemExit(1) from None
