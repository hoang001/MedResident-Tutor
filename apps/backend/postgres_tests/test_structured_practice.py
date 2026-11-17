"""Real PostgreSQL + ASGI routes, no Medical/Teaching provider permitted."""

import asyncio
import copy
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.common.enums import UserRole
from app.integration.clinical_cases import load_bundle
from app.integration.importer import persist_case
from app.modules.practice import router as routes
from app.modules.practice.models import PracticeAttempt
from app.modules.progress.models import LearningResult
from app.modules.questions.models import Question
from app.modules.users.models import User

BUNDLE = Path(__file__).resolve().parents[3] / "data/clinical-cases/exercises"


@pytest.fixture
async def structured(imported_schema, monkeypatch):
    from app.main import app

    engine, admin = imported_schema
    factory = async_sessionmaker(engine, expire_on_commit=False)
    cases = load_bundle(BUNDLE, structured=True)
    async with factory() as session, session.begin():
        for case, authored in cases:
            case.question["clinical_exercise"] = authored
            assert await persist_case(session, case, admin)
            assert not await persist_case(session, case, admin)
    monkeypatch.setattr(routes, "SessionFactory", factory)

    def forbidden():
        pytest.fail("Structured request must not even initialize a model/mock provider")

    monkeypatch.setattr(routes, "provider", forbidden)

    async def user():
        async with factory() as s:
            return await s.get(User, admin)

    app.dependency_overrides[routes.practice_user] = user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, factory, cases, admin
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("short", ["CASE01", "XR01"])
async def test_real_route_grades_pins_history_idempotency_and_rejects_input(
    structured, short, monkeypatch
):
    client, factory, cases, admin = structured
    case, _ = next(x for x in cases if x[0].question["question_id"].endswith(short))
    qid = case.question["question_id"]
    spec = case.question["structured_exercise"]
    body = {
        "question_id": qid,
        "revision_id": qid,
        "structured_answers": {
            p["id"]: p["correct_option_id"] for p in spec["parts"] if p["max_score"]
        },
    }
    pre = await client.get("/api/v1/practice/questions/" + qid)
    assert pre.status_code == 200
    for field in (
        "correct_option_id",
        "reference_answer",
        "annotations",
        "source_refs",
        "evidence_ids",
        "incorrect_feedback",
        "criterion_id",
        "source_image_id",
    ):
        assert '"' + field + '"' not in pre.text
    for invalid in ({"part_1": "bad"}, {"part_2": "r4c4"}, {"foreign": "o1"}):
        bad = await client.post(
            "/api/v1/practice/attempts",
            json={**body, "structured_answers": invalid},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert bad.status_code == 422
    for extra in (
        {"total_score": 2},
        {"student_answer": "do not grade essay"},
        {"revision_id": "wrong-revision"},
    ):
        assert (
            await client.post(
                "/api/v1/practice/attempts",
                json={**body, **extra},
                headers={"Idempotency-Key": uuid.uuid4().hex},
            )
        ).status_code == 422
    variants = [("correct", body["structured_answers"], 2), ("blank", {}, 0)]
    wrong = {
        p["id"]: next(o["id"] for o in p["options"] if o["id"] != p["correct_option_id"])
        for p in spec["parts"]
        if p["max_score"]
    }
    partial = {**wrong, "part_1": body["structured_answers"]["part_1"]}
    variants.extend(
        [
            ("incorrect", wrong, 0),
            ("partial", partial, 1),
            ("with_text", {**partial, "explanation": "  unchanged\n "}, 1),
        ]
    )
    saved = []
    for name, answers, expected in variants:
        payload = {**body, "structured_answers": answers}
        headers = {"Idempotency-Key": name}
        response = await client.post("/api/v1/practice/attempts", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "completed" and data["execution_mode"] == "structured"
        assert data["structured_result"]["total_score"] == expected
        assert data["medical_evaluation"] is None and data["teaching_feedback"] is None
        assert data["provider_metadata"] == {
            "grader": "deterministic-v1",
            "feedback": "authored-source-linked-v1",
            "model_calls": 0,
        }
        assert data["evidence"] and data["clinical_solution"]
        assert (await client.get("/api/v1/practice/attempts/" + data["id"])).json() == data
        assert (
            await client.post("/api/v1/practice/attempts", json=payload, headers=headers)
        ).json() == data
        assert (
            await client.post("/api/v1/practice/attempts/" + data["id"] + "/retry")
        ).json() == data
        saved.append(data)
    conflict = await client.post(
        "/api/v1/practice/attempts",
        json={**body, "structured_answers": {}},
        headers={"Idempotency-Key": "correct"},
    )
    assert conflict.status_code == 409
    # Concurrent replay reuses the same atomic completed attempt and no second grade.
    from app.modules.practice import service

    original_grade = service.grade
    grade_calls = []

    def counted_grade(*args):
        grade_calls.append(True)
        return original_grade(*args)

    monkeypatch.setattr(service, "grade", counted_grade)
    concurrent = await asyncio.gather(
        *(
            client.post(
                "/api/v1/practice/attempts", json=body, headers={"Idempotency-Key": "concurrent"}
            )
            for _ in range(3)
        )
    )
    assert len({r.json()["id"] for r in concurrent}) == 1
    assert len(grade_calls) == 1
    assert len((await client.get("/api/v1/practice/attempts")).json()) == 6
    async with factory() as s, s.begin():
        question = await s.scalar(select(Question).where(Question.external_id == qid))
        question.bank_version += 1
        question.content = "A future statement must not rewrite history"
        meta = copy.deepcopy(question.import_metadata)
        meta["dataset_fields"]["structured_exercise"]["parts"][0]["explanation"] = "future text"
        question.import_metadata = meta
    assert (await client.get("/api/v1/practice/attempts/" + saved[0]["id"])).json() == saved[0]
    async with factory() as s:
        row = await s.get(PracticeAttempt, uuid.UUID(saved[0]["id"]))
        assert row.snapshot["structured_exercise"] == spec
        assert row.snapshot["structured_answers"] == body["structured_answers"]
        assert await s.scalar(select(func.count()).select_from(LearningResult)) == 0


async def test_ownership_and_images_require_owner(structured):
    from app.main import app

    client, factory, cases, _ = structured
    qid = cases[0][0].question["question_id"]
    data = (
        await client.post(
            "/api/v1/practice/attempts",
            json={"question_id": qid, "revision_id": qid, "structured_answers": {}},
            headers={"Idempotency-Key": "owner"},
        )
    ).json()
    other = uuid.uuid4()
    async with factory() as s, s.begin():
        s.add(
            User(
                id=other,
                email="other@structured.invalid",
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
    asset = data["clinical_exercise"]["images"][0]["asset_id"]
    base = "/api/v1/practice/attempts/" + data["id"]
    assert (await client.get(base)).status_code == 404
    assert (await client.get(base + "/assets/" + asset)).status_code == 404
    assert (await client.post(base + "/retry")).status_code == 404
    assert (await client.get("/api/v1/practice/attempts")).json() == []
