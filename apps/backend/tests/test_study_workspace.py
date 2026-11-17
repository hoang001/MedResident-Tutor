import uuid

import pytest

from app.ai.providers.factory import create_embedding_provider, create_llm_provider
from app.core.config import Settings
from app.core.exceptions import AppError
from app.main import app
from app.modules.knowledge.service import get_graph_store, web_url
from app.modules.practice.providers import ServiceError, get_provider
from tests.knowledge_fixture import COURSE, ITEM, QUESTION, SOURCE, FixtureStore
from tests.test_api import create_admin_token, register_and_login


@pytest.fixture
def graph():
    store = FixtureStore()
    app.dependency_overrides[get_graph_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_graph_store, None)


async def login_headers(client):
    token = await register_and_login(client, f"study-{uuid.uuid4()}@example.com")
    return {"Authorization": f"Bearer {token}"}


async def test_library_requires_login_and_limits_scope(client, graph):
    assert (await client.get("/api/v1/knowledge/search")).status_code == 401
    assert (await client.get("/api/v1/knowledge/pdf/" + SOURCE)).status_code == 401
    headers = await login_headers(client)
    search = await client.get("/api/v1/knowledge/search?q=trat%20khop%20vai", headers=headers)
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["id"] == ITEM
    assert (
        await client.get("/api/v1/knowledge/search?limit=51", headers=headers)
    ).status_code == 422
    missing = await client.get("/api/v1/knowledge/node?id=FIXTURE:UNRELATED", headers=headers)
    assert missing.status_code == 404
    # Search strings never become Cypher, and unrelated nodes are excluded.
    quoted = await client.get(
        "/api/v1/knowledge/search", params={"q": "') DELETE n //"}, headers=headers
    )
    assert quoted.status_code == 200 and quoted.json()["total"] == 0
    question = await client.get("/api/v1/knowledge/node", params={"id": QUESTION}, headers=headers)
    assert "DO NOT EXPOSE" not in question.text
    assert "answer" not in question.json()
    assert question.json()["relations"][0]["target"]["id"] == ITEM


async def test_personal_records_are_scoped_versioned_and_not_mastery(client, graph):
    headers, other = await login_headers(client), await login_headers(client)
    payload = {
        "node_id": ITEM,
        "version": 0,
        "read_state": "read",
        "bookmarked": True,
        "note": "Private reading note",
    }
    result = await client.put("/api/v1/study/record", json=payload, headers=headers)
    assert result.status_code == 200 and result.json()["version"] == 1
    assert (
        await client.put("/api/v1/study/record", json=payload, headers=headers)
    ).status_code == 409
    mine = (await client.get("/api/v1/study/summary", headers=headers)).json()
    assert mine["read"] == 1 and mine["bookmarked"] == 1 and mine["mastery_assessed"] is False
    theirs = (await client.get("/api/v1/study/records", headers=other)).json()
    assert theirs == {"total": 0, "items": []}
    assert (
        await client.get("/api/v1/study/record", params={"node_id": ITEM}, headers=other)
    ).json()["note"] == ""
    payload["version"] = 1
    payload["note"] = "Updated note"
    assert (await client.put("/api/v1/study/record", json=payload, headers=headers)).json()[
        "version"
    ] == 2


async def test_session_snapshot_idempotency_ownership_and_no_grade(client, graph):
    headers, other = await login_headers(client), await login_headers(client)
    payload = {"idempotency_key": str(uuid.uuid4()), "question_ids": [QUESTION]}
    created = await client.post("/api/v1/study/sessions", json=payload, headers=headers)
    assert created.status_code == 201
    session = created.json()
    assert session["score"] is None and session["graded"] is False
    assert "DO NOT EXPOSE" not in created.text
    repeated = await client.post("/api/v1/study/sessions", json=payload, headers=headers)
    assert repeated.json()["id"] == session["id"]
    path = "/api/v1/study/sessions/" + session["id"]
    assert (await client.get(path, headers=other)).status_code == 404
    assert (
        await client.put(path, headers=other, json={"version": 1, "answers": {}})
    ).status_code == 404
    bad = {"version": 1, "answers": {ITEM: "Answer for a different item"}}
    assert (await client.put(path, headers=headers, json=bad)).status_code == 422
    answers = {QUESTION: "My answer"}
    saved = await client.put(path, headers=headers, json={"version": 1, "answers": answers})
    assert saved.status_code == 200 and saved.json()["version"] == 2
    assert (
        await client.put(path, headers=headers, json={"version": 1, "answers": answers})
    ).status_code == 409
    # Later graph edits do not replace the source/question snapshot or require a model.
    original = session["questions"][0]["title"]
    graph.value.nodes[QUESTION]["title"] = "Changed graph text"
    assert (await client.get(path, headers=headers)).json()["questions"][0]["title"] == original
    submitted = await client.put(
        path, headers=headers, json={"version": 2, "answers": answers, "submit": True}
    )
    assert submitted.json()["status"] == "submitted"
    repeat = await client.put(
        path, headers=headers, json={"version": 2, "answers": answers, "submit": True}
    )
    assert repeat.status_code == 200
    assert (
        await client.put(path, headers=headers, json={"version": 3, "answers": {}})
    ).status_code == 409
    assert (await client.get("/api/v1/study/summary", headers=headers)).json()["submitted"] == 1


async def test_reject_invalid_questions_and_idempotency_reuse(client, graph):
    headers = await login_headers(client)
    key = str(uuid.uuid4())
    for ids in [[], [ITEM], [QUESTION, QUESTION], ["missing"]]:
        result = await client.post(
            "/api/v1/study/sessions",
            headers=headers,
            json={"idempotency_key": str(uuid.uuid4()), "question_ids": ids},
        )
        assert result.status_code in (404, 422)
    result = await client.post(
        "/api/v1/study/sessions",
        headers=headers,
        json={"idempotency_key": key, "question_ids": [QUESTION]},
    )
    assert result.status_code == 201
    changed = await client.post(
        "/api/v1/study/sessions",
        headers=headers,
        json={"idempotency_key": key, "question_ids": [ITEM]},
    )
    assert changed.status_code == 409


async def test_admin_source_review_is_append_only_revision_aware(client, graph):
    learner = await login_headers(client)
    admin = {"Authorization": "Bearer " + await create_admin_token(client)}
    payload = {
        "node_id": ITEM,
        "revision": graph.value.get(ITEM)["revision"],
        "status": "source_checked",
        "note": "Compared with source page 8",
    }
    assert (
        await client.post("/api/v1/study/reviews", headers=learner, json=payload)
    ).status_code == 403
    created = await client.post("/api/v1/study/reviews", headers=admin, json=payload)
    assert created.status_code == 201 and created.json()["expert_approval"] is False
    graph.value.nodes[ITEM]["revision"] = "a" * 64
    assert (
        await client.post("/api/v1/study/reviews", headers=admin, json=payload)
    ).status_code == 409
    history = (
        await client.get("/api/v1/study/reviews", params={"node_id": ITEM}, headers=learner)
    ).json()
    assert len(history) == 1 and history[0]["current"] is False
    assert history[0]["expert_approval"] is False
    assert not any(k in history[0] for k in ("email", "hashed_password"))


async def test_curriculum_never_invents_course_content(client, graph):
    headers = await login_headers(client)
    result = await client.get("/api/v1/knowledge/curriculum", headers=headers)
    assert result.status_code == 200
    course = next(n for n in result.json()["nodes"] if n["id"] == COURSE)
    assert course["metadata"]["content_status"] == "awaiting_teacher_content"
    assert course["suggested_topics"] == []
    assert result.json()["current_program_confirmed"] is False


def test_pdf_containment_and_hmu_links(graph, tmp_path):
    root = tmp_path / "data"
    (root / "raw-source").mkdir(parents=True)
    (root / "raw-source/DVC.005844.pdf").write_bytes(b"%PDF-fixture")
    assert graph.value.pdf_path(SOURCE, root).name == "DVC.005844.pdf"
    (root / "escape.pdf").write_bytes(b"%PDF-fixture")
    graph.value.books[SOURCE]["filename"] = "../escape.pdf"
    with pytest.raises(AppError):
        graph.value.pdf_path(SOURCE, root)
    assert web_url("https://lms.hmu.edu.vn/course/view.php?id=1")
    for url in [
        "javascript:alert(1)",
        "https://hmu.edu.vn.evil.example/",
        "https://secret@lms.hmu.edu.vn/",
    ]:
        assert web_url(url) is None


def test_disabled_model_guard_precedes_any_external_provider():
    settings = Settings(
        _env_file=None,
        model_calls_enabled=False,
        practice_provider="http",
        llm_provider="external",
        embedding_provider="external",
    )
    for factory in (create_llm_provider, create_embedding_provider):
        with pytest.raises(AppError) as e:
            factory(settings)
        assert e.value.code == "MODEL_CALLS_DISABLED"
    with pytest.raises(ServiceError) as e:
        get_provider(settings)
    assert e.value.code == "MODEL_CALLS_DISABLED"
