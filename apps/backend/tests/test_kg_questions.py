import copy
import runpy
import uuid
from pathlib import Path

import pytest

from app.main import app
from app.modules.knowledge.service import get_graph_store
from app.modules.study.questions import question_bank
from tests.knowledge_fixture import ITEM as ORIGINAL_ITEM
from tests.knowledge_fixture import SOURCE, FixtureStore
from tests.test_api import create_admin_token, register_and_login

ITEM = "KGQFIXTURE:CONDITION"


@pytest.fixture
def graph():
    store = FixtureStore()
    store.value.nodes[ITEM] = store.value.nodes.pop(ORIGINAL_ITEM)
    store.value.nodes[ITEM]["id"] = ITEM
    for edge in store.value.edges:
        for key in ("start", "end"):
            if edge[key] == ORIGINAL_ITEM:
                edge[key] = ITEM
    # Unique source text/revision isolates reviewer decisions from other test modules.
    node = store.value.nodes[ITEM]
    node["revision"] = uuid.uuid4().hex * 2
    node["content"][0]["text"] = (
        "SOURCE_BASIS: keep conditions and exceptions in this synthetic exercise."
    )
    node["content"][0]["sources"][0]["excerpt"] = "PRIVATE_BASIS_BEFORE_SUBMISSION"
    second = copy.deepcopy(node)
    second.update(id="FIXTURE:INTERVENTION", title="Synthetic intervention", type="Intervention")
    store.value.nodes[second["id"]] = second
    store.value.edges.append(
        {
            "start": ITEM,
            "end": second["id"],
            "type": "MANAGED_WITH",
            "condition": "Only under synthetic condition X",
            "sources": node["sources"],
        }
    )
    app.dependency_overrides[get_graph_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_graph_store, None)


async def headers(client):
    token = await register_and_login(client, f"kgq-{uuid.uuid4()}@example.com")
    return {"Authorization": f"Bearer {token}"}


async def test_catalog_filters_and_no_answer_leak(client, graph):
    assert (await client.get("/api/v1/study/questions")).status_code == 401
    auth = await headers(client)
    response = await client.get("/api/v1/study/questions?origin=kg", headers=auth)
    body = response.json()
    assert response.status_code == 200 and body["total"] == 3
    assert not body["model_called"] and not body["expert_verified"] and not body["graded"]
    assert "PRIVATE_BASIS_BEFORE_SUBMISSION" not in response.text
    assert "SOURCE_BASIS" not in response.text and '"study_basis"' not in response.text
    assert {r["task"] for r in body["items"]} == {"source_recall", "source_relation"}
    repeat = (await client.get("/api/v1/study/questions?origin=kg", headers=auth)).json()
    assert [q["id"] for q in body["items"]] == [q["id"] for q in repeat["items"]]
    assert (await client.get("/api/v1/study/questions?book=unknown", headers=auth)).json()[
        "total"
    ] == 0
    assert (await client.get("/api/v1/study/questions?chapter=999", headers=auth)).json()[
        "total"
    ] == 0
    assert (await client.get("/api/v1/study/questions?q=DELETE%20n", headers=auth)).json()[
        "total"
    ] == 0
    assert (await client.get("/api/v1/study/questions?origin=book", headers=auth)).json()[
        "total"
    ] == 1
    assert (await client.get("/api/v1/study/questions?limit=51", headers=auth)).status_code == 422


async def test_reading_filters_are_user_scoped(client, graph):
    mine, other = await headers(client), await headers(client)
    payload = {"node_id": ITEM, "version": 0, "read_state": "read", "bookmarked": True, "note": ""}
    assert (await client.put("/api/v1/study/record", json=payload, headers=mine)).status_code == 200
    for focus in ("read", "bookmarked"):
        path = "/api/v1/study/questions?origin=kg&focus=" + focus
        assert (await client.get(path, headers=mine)).json()["total"] == 2
        assert (await client.get(path, headers=other)).json()["total"] == 0
    graph.value.nodes[ITEM]["revision"] = "f" * 64
    assert (await client.get("/api/v1/study/questions?origin=kg&focus=read", headers=mine)).json()[
        "total"
    ] == 0
    assert (
        await client.get("/api/v1/study/questions?origin=kg&focus=bookmarked", headers=mine)
    ).json()["total"] == 2


async def test_saved_basis_is_private_immutable_and_idempotent(client, graph):
    mine, other = await headers(client), await headers(client)
    candidates = (await client.get("/api/v1/study/questions?origin=kg", headers=mine)).json()[
        "items"
    ]
    question = next(q for q in candidates if q["task"] == "source_recall" and ITEM in q["node_ids"])
    data = {"idempotency_key": str(uuid.uuid4()), "question_ids": [question["id"]]}
    created = await client.post("/api/v1/study/sessions", json=data, headers=mine)
    assert created.status_code == 201 and "SOURCE_BASIS" not in created.text
    session = created.json()
    assert "study_basis" not in session["questions"][0]
    path = "/api/v1/study/sessions/" + session["id"]
    graph.value.nodes[ITEM]["content"][0]["text"] = "CHANGED_KG_CONTENT"
    graph.value.nodes[ITEM]["revision"] = "b" * 64
    repeat = await client.post("/api/v1/study/sessions", json=data, headers=mine)
    assert repeat.json()["id"] == session["id"]
    changed = await client.post(
        "/api/v1/study/sessions", json={**data, "idempotency_key": str(uuid.uuid4())}, headers=mine
    )
    assert changed.status_code == 409
    assert (await client.get(path, headers=other)).status_code == 404
    answers = {question["id"]: "My synthetic answer"}
    saved = await client.put(
        path, json={"version": session["version"], "answers": answers}, headers=mine
    )
    assert saved.status_code == 200 and "SOURCE_BASIS" not in saved.text
    submitted = await client.put(
        path,
        json={"version": saved.json()["version"], "answers": answers, "submit": True},
        headers=mine,
    )
    assert submitted.status_code == 200 and "SOURCE_BASIS" in submitted.text
    assert "CHANGED_KG_CONTENT" not in submitted.text
    assert submitted.json()["score"] is None and submitted.json()["graded"] is False
    assert submitted.json() == (await client.get(path, headers=mine)).json()


async def test_known_source_correction_blocks_new_questions(client, graph):
    admin = {"Authorization": "Bearer " + await create_admin_token(client)}
    learner = await headers(client)
    before = (await client.get("/api/v1/study/questions?origin=kg", headers=learner)).json()
    assert before["total"] == 3
    payload = {
        "node_id": ITEM,
        "revision": graph.value.nodes[ITEM]["revision"],
        "status": "needs_correction",
        "note": "Synthetic source correction",
    }
    assert (
        await client.post("/api/v1/study/reviews", json=payload, headers=admin)
    ).status_code == 201
    after = (await client.get("/api/v1/study/questions?origin=kg", headers=learner)).json()
    assert after["total"] == 1 and ITEM not in after["items"][0]["node_ids"]


def test_sources_remain_separate_and_incomplete_evidence_is_not_used(graph):
    snapshot = graph.value
    first = snapshot.nodes[ITEM]
    book2 = {
        **snapshot.books[SOURCE],
        "id": "OTHER_SOURCE",
        "year": 2006,
        "title": "Other source",
        "sha256": "1" * 64,
    }
    snapshot.books[book2["id"]] = book2
    ref = {**first["sources"][0], "source_id": book2["id"], "title": book2["title"]}
    first["content"].append(
        {"text": "A different statement under different source conditions", "sources": [ref]}
    )
    result = [
        q
        for q in question_bank(snapshot).values()
        if q.get("task") == "source_recall" and q["node_ids"] == [ITEM]
    ]
    assert len(result) == 2
    assert {q["book_ids"][0] for q in result} == {SOURCE, book2["id"]}
    assert all(len({r["source_id"] for r in q["sources"]}) == 1 for q in result)
    # An empty quote or an invalid file identity cannot support a fresh KG question.
    snapshot.books[SOURCE]["sha256"] = ""
    assert all(
        q.get("origin") == "book" or SOURCE not in q["book_ids"]
        for q in question_bank(snapshot).values()
    )
    first["content"] = [
        {"text": "unverified unsupported text", "sources": [{**ref, "excerpt": ""}]}
    ]
    assert not any(
        q.get("origin") == "kg_template" and q["node_ids"] == [ITEM]
        for q in question_bank(snapshot).values()
    )


def test_seed_helper_import_does_not_start_database_work(monkeypatch):
    def forbidden(_coroutine):
        raise AssertionError("Importing the fixture helper must not run seeding")
    monkeypatch.setattr("asyncio.run", forbidden)
    module = runpy.run_path(str(Path(__file__).parent / "e2e/seed.py"))
    assert callable(module["main"])
