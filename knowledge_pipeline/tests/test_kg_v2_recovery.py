import copy
import json

import httpx
import pytest

from document_toolkit.common import read_json, write_json
from knowledge_pipeline.kg_v2 import pipeline
from knowledge_pipeline.kg_v2.contracts import schemas
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.recovery import (
    project_records,
    recover_batch,
    recover_diagnostics,
)
from knowledge_pipeline.tests.test_kg_v2 import block, medical, support
from knowledge_pipeline.tests.test_kg_v2_draft import prepared, settings


def invalid_response():
    b = block()
    valid = medical(b)
    bad = medical(b, "empty", "Fracture")
    bad["content"] = []
    edge = {
        "local_id": "e",
        "from_id": "c",
        "to_id": "empty",
        "type": "IS_A",
        "condition": None,
        "sources": [support(b)],
    }
    return {"nodes": [valid, bad], "edges": [edge]}


def diagnostics(value, finish="stop"):
    return {
        "category": "schema",
        "attempts": [{"finish_reason": finish, "raw_response": json.dumps(value)}],
    }


def test_empty_content_does_not_discard_valid_peers_or_modify_original():
    original = invalid_response()
    before = copy.deepcopy(original)
    projected, rejected = project_records(original, schemas()[0])
    assert original == before
    assert len(projected["nodes"]) == 1 and len(rejected) == 1
    assert rejected[0]["candidate"]["content"] == []
    graph, audit = pipeline.compile_graph(
        {"w": projected}, [{"window_id": "w", "blocks": [block()]}], draft=True
    )
    assert len(graph["nodes"]) == 1 and not graph["edges"]
    assert audit["review_items"][0]["reason"] == "endpoint_not_in_draft_graph"
    dry_run_loader(graph)


def test_partial_recovery_refuses_malformed_envelope_or_truncated_text():
    with pytest.raises(ValueError, match="complete_original"):
        recover_diagnostics(diagnostics(invalid_response(), "length"), schemas()[0])
    with pytest.raises(ValueError):
        project_records({"nodes": [], "edges": [], "unknown": True}, schemas()[0])
    with pytest.raises(ValueError):
        project_records({"nodes": "broken", "edges": []}, schemas()[0])


def test_duplicate_local_ids_are_held_not_ambiguously_linked():
    row = medical(block())
    other = medical(block(), "independent")
    projected, rejected = project_records(
        {"nodes": [row, row, other], "edges": []}, schemas()[0]
    )
    assert [n["local_id"] for n in projected["nodes"]] == ["independent"]
    assert len(rejected) == 2 and all(
        r["reason"] == "duplicate_local_id_in_raw" for r in rejected
    )


def test_schema_projection_checkpoints_real_response_without_retry(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(pipeline, "prepare", prepared)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": json.dumps(invalid_response())},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    monkeypatch.setattr(
        pipeline.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond)
    )
    scope = tmp_path / "scope.json"
    write_json(scope, {"ids": ["w"]})
    output = tmp_path / "data/knowledge-extraction/v2/projection"
    previous_error = output / "audit/raw/w.attempt-1.error.json"
    write_json(previous_error, {"previous_invocation": True})
    previous_error_bytes = previous_error.read_bytes()
    opts = {
        "draft": True,
        "settings": settings(),
        "root": tmp_path,
        "draft_registry_path": tmp_path / "ids.json",
    }
    report = pipeline.run(scope, output, **opts)
    assert len(calls) == 1 and report["partial_schema_windows"] == ["w"]
    assert previous_error.read_bytes() == previous_error_bytes
    assert (output / "audit/raw/w.attempt-1.event-2.error.json").exists()
    assert report["rejected_items"] == 1 and report["draft_nodes"] == 1
    assert (
        read_json(output / "audit/raw/w.original-response.json") == invalid_response()
    )
    again = pipeline.run(scope, output, resume=True, **opts)
    assert len(calls) == 1 and again["cache_hits_this_run"] == 1
    assert again["rejected_items"] == 1


def test_offline_batch_recovery_keeps_source_and_writes_new_review(
    monkeypatch, tmp_path
):
    import knowledge_pipeline.kg_v2.revalidate as module

    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    source = tmp_path / "data/knowledge-extraction/v2/old"
    shard = source / "shards/one"
    a = shard / "audit"
    write_json(source / "batch-state.json", {"shards": {"one": {}}})
    write_json(a / "manifest.json", {"mode": "test_original_source"})
    write_json(a / "extraction.schema.json", schemas()[0])
    write_json(a / "windows.json", [{"window_id": "w", "blocks": [block()]}])
    write_json(a / "catalog.json", [])
    (a / "pages.jsonl").write_text("", encoding="utf-8")
    error_file = a / "raw/w.attempt-1.error.json"
    write_json(error_file, diagnostics(invalid_response()))
    original_bytes = error_file.read_bytes()
    output = tmp_path / "data/knowledge-extraction/v2/recovered"
    result = recover_batch(source, output, draft_registry_path=tmp_path / "ids.json")
    assert result["llm_calls_this_run"] == 0 and result["result"]["draft_nodes"] == 1
    assert result["result"]["partial_schema_windows"] == ["w"]
    assert error_file.read_bytes() == original_bytes
    assert (output / "aggregate/review.html").exists()
    assert (
        read_json(output / "aggregate/audit/raw/w.original-response.json")
        == invalid_response()
    )
