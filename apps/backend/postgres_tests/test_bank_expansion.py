import copy

from sqlalchemy import select

from app.modules.questions.models import Question
from postgres_tests.test_question_bank import BODY
from postgres_tests.test_question_bank import bank as bank_fixture  # noqa: F401


async def test_topic_search_pagination_and_no_gold(bank_fixture):  # noqa: F811
    client, factory, state, admin, learner = bank_fixture
    ids = []
    for title, topic in [
        ("Đau khuỷu", "Chi trên"),
        ("Đau háng", "Chi dưới"),
        ("Khám khuỷu", "Chi trên"),
    ]:
        body = {**copy.deepcopy(BODY), "content": title, "topic": topic}
        q = (await client.post("/api/v1/admin/questions", json=body)).json()
        r = await client.patch(
            "/api/v1/admin/questions/" + q["question_id"] + "/availability",
            json={"is_available": True, "version": q["version"]},
        )
        assert r.status_code == 200, r.text
        ids.append(q["question_id"])
    # A fourth, unpublished item must never enter student catalog/results.
    draft = (await client.post("/api/v1/admin/questions", json=BODY)).json()
    state["user"] = learner
    all_items = (await client.get("/api/v1/practice/questions")).json()
    first = (await client.get("/api/v1/practice/catalog?limit=2&offset=0")).json()
    second = (await client.get("/api/v1/practice/catalog?limit=2&offset=2")).json()
    assert first["total"] == 3 and first["available_total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert {x["question_id"] for x in first["items"]}.isdisjoint(
        {x["question_id"] for x in second["items"]}
    )
    for item in all_items:
        assert set(item) == {"question_id", "question", "topic"}
    matched = (
        await client.get("/api/v1/practice/catalog", params={"q": "khuYU", "topic": "Chi trên"})
    ).json()
    assert matched["total"] == 2
    assert (await client.get("/api/v1/practice/catalog?offset=100")).json()["items"] == []
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert (await client.get("/api/v1/practice/catalog?" + query)).status_code == 422
    assert (
        await client.get("/api/v1/practice/questions/" + second["items"][0]["question_id"])
    ).status_code == 200
    assert (
        await client.get("/api/v1/practice/questions/" + draft["question_id"])
    ).status_code == 404


async def test_codex_publication_records_actual_actor(bank_fixture):  # noqa: F811
    from app.ai.retrieval.evidence import digest
    from app.modules.questions.publication import publish

    client, factory, state, admin, learner = bank_fixture
    draft = (await client.post("/api/v1/admin/questions", json=BODY)).json()
    review = {
        "actor": "Codex",
        "method": "manual_source_comparison",
        "human_reviewed": False,
        "clinician_approved": False,
    }
    async with factory() as s, s.begin():
        q = await s.scalar(
            select(Question).where(Question.external_id == draft["question_id"]).with_for_update()
        )
        await publish(s, q, admin, review=review)
        package = q.import_metadata["approved_package"]
        assert package["approved_by"] == "Codex" and package["import_account_id"] == str(admin)
        assert package["expert_verified"] is False
        assert package["source_review"] == review
        assert package["sha256"] == digest({k: v for k, v in package.items() if k != "sha256"})
        assert package["payload"]["rubric"]["reference_answer"] == BODY["reference_answer"]
        assert package["provenance"] and all(x["sha256"] for x in package["provenance"])
