from app.modules.questions import authoring
from postgres_tests.test_question_bank import bank as bank_fixture  # noqa: F401


async def test_ai_review_is_required_and_audited_before_question_storage(bank_fixture):  # noqa: F811
    from sqlalchemy import func, select

    from app.modules.questions.models import Question

    client, factory, state, admin, learner = bank_fixture
    scope = authoring.Scope(question="Synthetic review gate", max_score=1)
    token = authoring.seal(
        {
            "scope": scope.model_dump(),
            "proposal": {
                "reference_answer": "Original AI wording",
                "criteria": [],
                "insufficient_basis": [],
            },
            "mode": "synthetic_test",
        },
        "proposal",
    )
    body = {
        "content": scope.question,
        "rubric_name": "R",
        "max_score": 1,
        "reference_answer": "Admin edited answer",
        "proposal_token": token,
        "criteria": [
            {"description": "Condition A", "max_score": 1, "source_unit_ids": ["FIXTURE_SU_A"]}
        ],
    }
    async with factory() as session:
        before = await session.scalar(select(func.count()).select_from(Question))
    response = await client.post("/api/v1/admin/questions", json=body)
    assert response.status_code == 422
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Question)) == before
    response = await client.post(
        "/api/v1/admin/questions", json={**body, "proposal_reviewed": True}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["reference_answer"] == "Admin edited answer" and not result["is_available"]
    async with factory() as session:
        row = await session.scalar(
            select(Question).where(Question.external_id == result["question_id"])
        )
        assert row.import_metadata["authoring"]["proposal_reviewed_by"] == str(admin)


async def test_approved_package_workflow(bank_fixture, monkeypatch):  # noqa: F811
    client, factory, state, admin, learner = bank_fixture
    scope = authoring.Scope(
        question="New independent authoring question", topic="Topic", max_score=1
    )
    body = {
        "content": scope.question,
        "rubric_name": "Draft",
        "max_score": 1,
        "reference_answer": "Reference answer",
        "criteria": [],
    }
    draft = (await client.post("/api/v1/admin/questions", json=body)).json()
    assert draft["criteria"] == [] and not draft["is_available"]
    path = "/api/v1/admin/questions/" + draft["question_id"]
    assert (
        await client.patch(
            path + "/availability", json={"version": draft["version"], "is_available": True}
        )
    ).status_code == 422
    body.update(
        version=draft["version"],
        criteria=[
            {
                "description": "Source-backed criterion",
                "max_score": 1,
                "source_unit_ids": ["FIXTURE_SU_A"],
            }
        ],
    )
    response = await client.put(path, json=body)
    assert response.status_code == 200, response.text
    ready = response.json()
    response = await client.patch(
        path + "/availability", json={"version": ready["version"], "is_available": True}
    )
    assert response.status_code == 200, response.text
    published = response.json()
    assert published["approved_package_hash"]

    # Any retrieval invocation here is a regression, including strategy hybrid.
    def forbidden(*a, **kw):
        raise AssertionError("KG/vector must not be called")

    monkeypatch.setattr("app.ai.retrieval.factory.create_retriever", forbidden)
    monkeypatch.setattr("app.ai.retrieval.factory.is_textbook_question", forbidden)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "practice_retrieval_strategy", "hybrid")
    from app.modules.practice import router as practice_router
    from app.modules.practice.providers import MockProvider

    provider = MockProvider("teaching_error")
    original_evaluate = provider.evaluate
    captured = []

    async def evaluate(stage, payload, retry=False):
        if stage == "medical":
            import copy

            captured.append(copy.deepcopy(payload))
        return await original_evaluate(stage, payload, retry)

    provider.evaluate = evaluate
    monkeypatch.setattr(practice_router, "get_provider", lambda *args: provider)
    state["user"] = learner
    for endpoint in ["retrieve", "materialize", "propose"]:
        assert (
            await client.post("/api/v1/admin/authoring/" + endpoint, json={})
        ).status_code == 403
    listing = (await client.get("/api/v1/practice/questions")).json()
    assert all(set(q) == {"question_id", "question"} for q in listing)
    response = await client.post(
        "/api/v1/practice/attempts",
        json={"question_id": published["question_id"], "student_answer": "Response"},
        headers={"Idempotency-Key": "authoring-first"},
    )
    assert response.status_code == 200, response.text
    attempt = response.json()
    assert attempt["medical_evaluation"] is not None
    assert attempt["stage_error"]["stage"] == "teaching"
    assert captured[0]["evidence"] == attempt["evidence"]
    assert captured[0]["rubric"]["reference_answer"] == "Reference answer"
    import json
    from pathlib import Path

    proof = (
        Path(__file__).resolve().parents[3]
        / "data/authoring/checks-20261112/approved-package-proof.json"
    )
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text(
        json.dumps(
            {
                "mode": "mock_medical_teaching_failure",
                "retrieval_calls_forbidden": True,
                "medical_payload": captured[0],
                "attempt_trace": attempt["retrieval"],
                "medical_retained": True,
                "stage_error": attempt["stage_error"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert attempt["retrieval"]["effective_strategy"] == "approved_package"
    assert attempt["retrieval"]["neo4j_queries"] == 0
    assert attempt["retrieval"]["vector_search"] is False
    state["user"] = admin
    body.update(version=published["version"], reference_answer="Revised answer")
    response = await client.put(path, json=body)
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised["question_id"] != published["question_id"] and not revised["is_available"]
    assert revised["previous_revision"] == published["question_id"]
    old = (await client.get(path)).json()
    assert old["reference_answer"] == "Reference answer" and old["is_available"]
    state["user"] = learner
    history = await client.get("/api/v1/practice/attempts/" + attempt["id"])
    assert history.status_code == 200
    assert history.json()["snapshot_hash"] == attempt["snapshot_hash"]


async def test_selected_source_sync_is_idempotent(bank_fixture):  # noqa: F811
    client, factory, state, admin, learner = bank_fixture
    evidence = {
        "source_unit_id": "CORPUS_ONLY_RB1",
        "source_id": "NEW_BOOK",
        "title": "A source window",
        "content": "Complete source with conditions.",
        "page_start": 7,
        "page_end": 7,
    }
    provenance = {"source_unit_id": "CORPUS_ONLY_RB1", "source_id": "NEW_BOOK", "sha256": "a" * 64}
    token = authoring.seal(
        {"evidence": [evidence], "provenance": [provenance], "trace": {}}, "evidence"
    )
    body = {"bundle_token": token, "selected_ids": ["CORPUS_ONLY_RB1"]}
    first = await client.post("/api/v1/admin/authoring/materialize", json=body)
    second = await client.post("/api/v1/admin/authoring/materialize", json=body)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    assert first.json()[0]["source_unit_id"].startswith("AUTH_SU_")
    assert first.json()[0]["retrieval_id"] == "CORPUS_ONLY_RB1"
