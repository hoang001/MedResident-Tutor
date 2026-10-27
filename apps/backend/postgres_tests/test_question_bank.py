import copy
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.common.enums import UserRole
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.practice import router as practice_routes
from app.modules.questions import router as bank_routes
from app.modules.questions.models import Question, RubricCriterion
from app.modules.users.models import User
from tests.e2e.bank_fixtures import seed_sources

BODY = {
    "content": "Synthetic question",
    "rubric_name": "Synthetic rubric",
    "max_score": 6,
    "criteria": [
        {
            "description": f"Synthetic criterion {i}",
            "max_score": i,
            "source_unit_ids": ["FIXTURE_SU_A"] if i == 1 else ["FIXTURE_SU_A", "FIXTURE_SU_B"],
        }
        for i in (1, 2, 3)
    ],
}


@pytest.fixture
async def bank(imported_schema, tmp_path, monkeypatch):
    engine, admin = imported_schema
    factory = async_sessionmaker(engine, expire_on_commit=False)
    learner = uuid.uuid4()
    async with factory() as s, s.begin():
        await seed_sources(s, admin, tmp_path / "sources")
        s.add(
            User(
                id=learner,
                email="bank-learner@example.com",
                full_name="Test",
                hashed_password="not-login",
                role=UserRole.LEARNER,
                is_active=True,
            )
        )
    monkeypatch.setattr(bank_routes, "SessionFactory", factory)
    monkeypatch.setattr(practice_routes, "SessionFactory", factory)
    state = {"user": admin}

    async def signed_in():
        async with factory() as s:
            return await s.get(User, state["user"])

    app.dependency_overrides[get_current_user] = signed_in
    app.dependency_overrides[practice_routes.practice_user] = signed_in
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, factory, state, admin, learner
    finally:
        app.dependency_overrides.clear()


async def test_bank_lifecycle_and_immutable_attempt(bank):
    client, factory, state, admin, learner = bank
    created = await client.post("/api/v1/admin/questions", json=BODY)
    assert created.status_code == 201, created.text
    q = created.json()
    path = "/api/v1/admin/questions/" + q["question_id"]
    assert q["question_id"].startswith("APP_Q_") and not q["is_available"]
    assert len(q["criteria"]) == 3 and q["topic_id"] is None
    ids = [x["criterion_id"] for x in q["criteria"]]
    assert len(set(ids)) == 3
    state["user"] = learner
    assert (await client.get("/api/v1/practice/questions")).json() == []
    assert (
        await client.post(
            "/api/v1/practice/attempts",
            json={"question_id": q["question_id"], "student_answer": "Runtime"},
            headers={"Idempotency-Key": "inactive"},
        )
    ).status_code == 404
    state["user"] = admin
    q = (
        await client.patch(
            path + "/availability", json={"version": q["version"], "is_available": True}
        )
    ).json()
    state["user"] = learner
    listing = (await client.get("/api/v1/practice/questions")).json()
    assert set(listing[0]) == {"question_id", "question"}
    result = await client.post(
        "/api/v1/practice/attempts",
        json={"question_id": q["question_id"], "student_answer": "Runtime"},
        headers={"Idempotency-Key": "active"},
    )
    assert result.status_code == 200, result.text
    attempt = result.json()
    assert attempt["status"] == "completed"
    assert len(attempt["medical_evaluation"]["rubric_scores"]) == 3
    assert attempt["medical_evaluation"]["max_score"] == 6 and len(attempt["evidence"]) == 2
    state["user"] = admin
    update = copy.deepcopy(BODY)
    update.update(version=q["version"], content="Changed current question", max_score=8)
    update["criteria"] = [
        {**BODY["criteria"][0], "criterion_id": ids[0]},
        {**BODY["criteria"][2], "criterion_id": ids[2]},
        {
            "description": "New fourth criterion",
            "max_score": 4,
            "source_unit_ids": ["FIXTURE_SU_B"],
        },
    ]
    response = await client.put(path, json=update)
    assert response.status_code == 200, response.text
    q = response.json()
    assert [c["criterion_id"] for c in q["criteria"]][:2] == [ids[0], ids[2]]
    assert ids[1] not in [c["criterion_id"] for c in q["criteria"]]
    assert (await client.put(path, json=update)).status_code == 409
    assert (
        await client.patch(
            path + "/availability", json={"version": q["version"], "is_available": False}
        )
    ).status_code == 200
    state["user"] = learner
    assert (await client.get("/api/v1/practice/questions")).json() == []
    assert (await client.get("/api/v1/practice/questions/" + q["question_id"])).status_code == 404
    assert (await client.get("/api/v1/practice/attempts/" + attempt["id"])).json() == attempt
    # Existing idempotent submission still returns the historical attempt after retirement.
    assert (
        await client.post(
            "/api/v1/practice/attempts",
            json={"question_id": q["question_id"], "student_answer": "Runtime"},
            headers={"Idempotency-Key": "active"},
        )
    ).json()["id"] == attempt["id"]
    assert (
        await client.post(
            "/api/v1/practice/attempts",
            json={"question_id": q["question_id"], "student_answer": "Runtime"},
            headers={"Idempotency-Key": "new-after-retirement"},
        )
    ).status_code == 404
    for method, payload, pathpart in (
        ("get", None, "/admin/questions"),
        ("post", BODY, "/admin/questions"),
        ("get", None, "/admin/source-units"),
        ("get", None, "/admin/source-units/FIXTURE_SU_A"),
        ("get", None, path.removeprefix("/api/v1")),
        ("put", update, path.removeprefix("/api/v1")),
        (
            "patch",
            {"version": q["version"], "is_available": True},
            path.removeprefix("/api/v1") + "/availability",
        ),
    ):
        assert (
            await client.request(
                method, "/api/v1" + pathpart, **({"json": payload} if payload is not None else {})
            )
        ).status_code == 403


@pytest.mark.parametrize(
    "mutation", ["missing", "unknown", "negative", "infinite", "duplicate_id", "wrong_total"]
)
async def test_invalid_bank_input_rolls_back(bank, mutation):
    client, factory, _, _, _ = bank
    body = copy.deepcopy(BODY)
    if mutation == "missing":
        body["criteria"][0]["source_unit_ids"] = []
    if mutation == "unknown":
        body["criteria"][0]["source_unit_ids"] = ["MISSING"]
    if mutation == "negative":
        body["criteria"][0]["max_score"] = -1
    if mutation == "infinite":
        raw = json.dumps(body).replace('"max_score": 6', '"max_score": 1e999', 1)
        response = await client.post(
            "/api/v1/admin/questions", content=raw, headers={"Content-Type": "application/json"}
        )
    elif mutation == "duplicate_id":
        body["criteria"][0]["criterion_id"] = "duplicate"
        body["criteria"][1]["criterion_id"] = "duplicate"
    elif mutation == "wrong_total":
        body["max_score"] = 99
    if mutation != "infinite":
        response = await client.post("/api/v1/admin/questions", json=body)
    assert response.status_code == 422, response.text
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(Question)) == 0
        assert await s.scalar(select(func.count()).select_from(RubricCriterion)) == 0


async def test_edit_failure_is_atomic_and_publish_revalidates_source(bank):
    client, factory, _, _, _ = bank
    q = (await client.post("/api/v1/admin/questions", json=BODY)).json()
    path = "/api/v1/admin/questions/" + q["question_id"]
    body = copy.deepcopy(BODY)
    body.update(version=q["version"], content="Should roll back")
    body["criteria"][0]["criterion_id"] = "foreign-criterion-id"
    assert (await client.put(path, json=body)).status_code == 422
    assert (await client.get(path)).json() == q
    async with factory() as s, s.begin():
        await s.execute(text("UPDATE documents SET source_sha256=NULL"))
    assert (
        await client.patch(
            path + "/availability", json={"version": q["version"], "is_available": True}
        )
    ).status_code == 422
    assert not (await client.get(path)).json()["is_available"]
