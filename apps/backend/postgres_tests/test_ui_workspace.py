"""UI catalog/privacy contracts against a disposable PostgreSQL database."""

import copy

from sqlalchemy import select

from app.modules.questions.models import Question
from postgres_tests.test_question_bank import BODY

pytest_plugins = ("postgres_tests.test_question_bank",)


async def test_read_catalogs_history_and_role_boundaries(bank):
    client, _, state, admin, learner = bank
    q = (await client.post("/api/v1/admin/questions", json=BODY)).json()
    base = "/api/v1/admin/questions/" + q["question_id"]
    catalog = (await client.get("/api/v1/admin/question-catalog?limit=1")).json()
    assert catalog["counts"] == dict(all=1, published=0, draft=1, review=1)
    assert catalog["total"] == len(catalog["items"]) == 1
    assert (await client.get("/api/v1/admin/question-catalog?offset=1")).json()["items"] == []
    assert (await client.get("/api/v1/admin/question-catalog?q=no-match")).json()["total"] == 0
    source = (await client.get("/api/v1/admin/source-catalog?q=FIXTURE_SU_A&limit=1")).json()
    assert source["total"] == len(source["items"]) == 1
    assert source["items"][0]["source_unit_id"] == "FIXTURE_SU_A"
    config = (await client.get("/api/v1/admin/authoring/config")).json()
    assert config == dict(proposal_available=False, manual_authoring_available=True)
    q = (
        await client.patch(
            base + "/availability", json={"version": q["version"], "is_available": True}
        )
    ).json()
    state["user"] = learner
    available = (await client.get("/api/v1/practice/catalog")).json()
    assert available["total"] == available["available_total"] == 1
    assert not {"reference_answer", "criteria", "evidence", "rubric"} & available["items"][0].keys()
    attempt = (
        await client.post(
            "/api/v1/practice/attempts",
            json={
                "question_id": q["question_id"],
                "student_answer": "Synthetic answer",
            },
            headers={"Idempotency-Key": "ui-privacy-test"},
        )
    ).json()
    assert attempt["status"] == "completed"
    page = (
        await client.get("/api/v1/practice/history?status=completed&q=Synthetic&limit=1")
    ).json()
    assert page["total"] == page["completed_total"] == page["overall_total"] == 1
    assert page["items"] == [attempt]
    assert (await client.get("/api/v1/practice/history?status=attention")).json()["total"] == 0
    available = (await client.get("/api/v1/practice/catalog")).json()["items"][0]
    assert (
        available["attempt_status"] == "completed" and available["last_attempt_id"] == attempt["id"]
    )
    for path in ("question-catalog", "source-catalog", "authoring/config"):
        assert (await client.get("/api/v1/admin/" + path)).status_code == 403
    state["user"] = admin
    assert (await client.get("/api/v1/practice/history")).json()["total"] == 0
    assert (await client.get("/api/v1/practice/attempts/" + attempt["id"])).status_code == 404
    assert (await client.get("/api/v1/practice/catalog")).json()["items"][0].get(
        "last_attempt_id"
    ) is None


async def test_legacy_published_edit_creates_draft_revision(bank):
    client, factory, _, _, _ = bank
    original = (await client.post("/api/v1/admin/questions", json=BODY)).json()
    # Simulate a legacy available question with no immutable approved package.
    async with factory() as session, session.begin():
        row = await session.scalar(
            select(Question).where(Question.external_id == original["question_id"])
        )
        row.is_available = True
    body = {**copy.deepcopy(BODY), "version": original["version"], "content": "Changed legacy"}
    updated = await client.put("/api/v1/admin/questions/" + original["question_id"], json=body)
    assert updated.status_code == 200, updated.text
    revision = updated.json()
    assert revision["question_id"] != original["question_id"]
    assert revision["previous_revision"] == original["question_id"] and not revision["is_available"]
    unchanged = (await client.get("/api/v1/admin/questions/" + original["question_id"])).json()
    assert unchanged["content"] == original["content"] and unchanged["is_available"]
