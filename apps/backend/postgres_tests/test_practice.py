import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.common.enums import UserRole
from app.integration.importer import import_case
from app.modules.practice import router as routes
from app.modules.practice.contracts import ServiceError
from app.modules.practice.models import PracticeAttempt
from app.modules.practice.providers import MockProvider, get_provider
from app.modules.practice.service import owned, process, submit
from app.modules.progress.models import LearningResult
from app.modules.users.models import User
from postgres_tests.conftest import MANIFEST

QID = "ORTHO_B21CN1_Q_0001"


@pytest.fixture
async def practice(imported_schema, case_repo, tmp_path, monkeypatch):
    engine, admin = imported_schema
    await import_case(engine, case_repo, MANIFEST, admin, tmp_path / "storage")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(routes, "SessionFactory", factory)
    return factory, admin


async def load(factory, admin, aid):
    async with factory() as session:
        return await owned(session, admin, aid)


async def test_success_reload_and_isolation(practice, monkeypatch):
    from app.main import app

    factory, admin = practice
    p = MockProvider()
    monkeypatch.setattr(routes, "provider", lambda: p)

    async def user():
        async with factory() as s:
            return await s.get(User, admin)

    app.dependency_overrides[routes.practice_user] = user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            qs = (await client.get("/api/v1/practice/questions")).json()
            assert set(qs[0]) == {"question_id", "question"}
            detail = (await client.get("/api/v1/practice/questions/" + QID)).json()
            assert detail == qs[0]
            body = {"question_id": QID, "student_answer": "Runtime answer"}
            res = await client.post(
                "/api/v1/practice/attempts", json=body, headers={"Idempotency-Key": "one"}
            )
            assert res.status_code == 200, res.text
            data = res.json()
            assert data["status"] == "completed"
            assert data["execution_mode"] == "mock"
            assert len(data["medical_evaluation"]["rubric_scores"]) == 2
            assert data["medical_evaluation"]["max_score"] == 2
            assert len(data["evidence"]) == 1
            assert data["evidence"][0]["page_start"] == 16
            assert data["provenance"][0]["printed_page_start"] == 15
            assert len(data["snapshot_hash"]) == 64
            assert "reference_answer" not in str(data)
            repeat = await client.post(
                "/api/v1/practice/attempts", json=body, headers={"Idempotency-Key": "one"}
            )
            assert repeat.json()["id"] == data["id"]
            assert p.calls == {"medical": 1, "teaching": 1}
            conflict = await client.post(
                "/api/v1/practice/attempts",
                json={**body, "student_answer": "Different"},
                headers={"Idempotency-Key": "one"},
            )
            assert conflict.status_code == 409
        # New HTTP client simulates reload, with data read from PostgreSQL.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/practice/attempts/" + data["id"])).json() == data
            assert len((await client.get("/api/v1/practice/attempts")).json()) == 1
        other = uuid.uuid4()
        async with factory() as s, s.begin():
            s.add(
                User(
                    id=other,
                    email="other@example.invalid",
                    full_name="Other",
                    hashed_password="not-login",
                    role=UserRole.LEARNER,
                    is_active=True,
                )
            )

        async def other_user():
            async with factory() as s:
                return await s.get(User, other)

        app.dependency_overrides[routes.practice_user] = other_user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/practice/attempts/" + data["id"])).status_code == 404
            assert (
                await client.post("/api/v1/practice/attempts/" + data["id"] + "/retry")
            ).status_code == 404
            assert (await client.get("/api/v1/practice/attempts")).json() == []
        async with factory() as s:
            assert await s.scalar(select(func.count()).select_from(LearningResult)) == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "scenario,status,code",
    [
        ("medical_error", "medical_failed", "PROVIDER_FAILED"),
        ("medical_invalid", "medical_failed", "MODEL_OUTPUT_TOTAL_MISMATCH"),
        ("teaching_error", "teaching_failed", "PROVIDER_FAILED"),
        ("teaching_invalid", "teaching_failed", "TEACHING_ALIGNMENT_INVALID"),
        ("timeout", "medical_failed", "PROVIDER_TIMEOUT"),
        ("busy", "medical_failed", "PROVIDER_BUSY"),
    ],
)
async def test_errors_persist(practice, scenario, status, code):
    factory, admin = practice
    p = MockProvider(scenario)
    aid, _ = await submit(factory, admin, QID, "Answer", "key", p)
    await process(factory, admin, aid, p, 5)
    row = await load(factory, admin, aid)
    assert row.status == status
    assert row.stage_error["code"] == code
    assert (row.medical_evaluation is not None) == status.startswith("teaching")
    assert row.teaching_feedback is None
    if scenario == "teaching_error":
        original = row.medical_evaluation
        medical_invocation = row.provider_metadata["medical"]["invocation_id"]
        await process(factory, admin, aid, p, 5, retry=True)
        row = await load(factory, admin, aid)
        assert row.status == "completed"
        assert row.medical_evaluation == original
        assert row.provider_metadata["medical"]["invocation_id"] == medical_invocation
        assert p.calls == {"medical": 1, "teaching": 2}


async def test_concurrent_idempotency_and_claims(practice):
    factory, admin = practice
    p = MockProvider()
    results = await asyncio.gather(
        *(submit(factory, admin, QID, "Answer", "same", p) for _ in range(5))
    )
    assert len({r[0] for r in results}) == 1
    assert sum(r[1] for r in results) == 1
    aid = results[0][0]
    await asyncio.gather(*(process(factory, admin, aid, p, 5) for _ in range(5)))
    assert p.calls == {"medical": 1, "teaching": 1}
    assert (await load(factory, admin, aid)).status == "completed"
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(PracticeAttempt)) == 1


async def test_authentication_required(practice):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/practice/questions")).status_code == 401


async def test_actual_timeout_and_expired_claim(practice):
    from datetime import UTC, datetime, timedelta

    factory, admin = practice

    class Slow(MockProvider):
        async def evaluate(self, *args, **kwargs):
            await asyncio.sleep(5)

    aid, _ = await submit(factory, admin, QID, "Answer", "slow", Slow())
    await process(factory, admin, aid, Slow(), 0.01)
    assert (await load(factory, admin, aid)).stage_error["code"] == "PROVIDER_TIMEOUT"
    async with factory() as s, s.begin():
        row = await owned(s, admin, aid)
        row.status = "medical_running"
        row.claim_token = uuid.uuid4()
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    await process(factory, admin, aid, MockProvider(), 5, retry=True)
    assert (await load(factory, admin, aid)).status == "completed"


def test_mock_forbidden_outside_development():
    from app.core.config import Settings

    with pytest.raises(ServiceError, match="MOCK_FORBIDDEN"):
        get_provider(Settings(app_env="production", practice_provider="mock"))
