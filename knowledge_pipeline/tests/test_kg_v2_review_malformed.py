"""Rejected arbitrary JSON must remain reviewable without entering the graph."""

import copy
import json

import pytest

from document_toolkit.common import read_json
from knowledge_pipeline.kg_v2.draft import write_review_output
from knowledge_pipeline.kg_v2.pipeline import compile_graph
from knowledge_pipeline.tests.test_kg_v2 import block, medical


@pytest.mark.parametrize("kind", ["Intervention", "Classification"])
def test_unknown_content_citation_holds_only_that_record(kind):
    source = block()
    invalid = medical(source, "bad", "Fracture", kind)
    invalid["content"][0]["sources"] = [{"block_id": "invented"}]
    graph, audit = compile_graph(
        {"w": {"nodes": [medical(source), invalid], "edges": []}},
        [{"window_id": "w", "blocks": [source]}],
        draft=True,
    )
    assert len(graph["nodes"]) == 1
    assert audit["rejected"][0]["reason"] == "unknown_block"
    assert audit["rejected"][0]["candidate"] == invalid


@pytest.mark.parametrize(
    "candidate",
    [
        {"content": [{"sources": {"block_id": "b", "excerpt": "Example"}}]},
        {"content": [{"text": "Missing sources"}]},
        {"content": [None, "bad", 1, {"sources": ["block_id", None, {}]}]},
        {"sources": None, "identity_sources": "bad", "basis_sources": 3},
        {"content": None},
        {"sources": {"block_id": "b"}},
        "not an object",
    ],
)
def test_malformed_held_records_are_preserved_and_export_cannot_crash(
    tmp_path, candidate
):
    before = copy.deepcopy(candidate)
    graph = {"schema_version": "medical-kg-v2", "nodes": [], "edges": []}
    audit = {
        "review_items": [{"reason": "invalid_record_schema", "candidate": candidate}],
        "rejected": [{"reason": "invalid_record_schema", "candidate": candidate}],
    }
    block = {
        "block_id": "b",
        "source_id": "book",
        "pdf_page": 1,
        "printed_page_label": None,
        "text": "Example",
        "kind": "body",
    }
    write_review_output(
        tmp_path, graph, audit, [{"blocks": [block], "window_id": "w"}], [], {}
    )
    assert candidate == before
    rows = [
        json.loads(line)
        for line in (tmp_path / "review-items.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    held = next(r for r in rows if r["reason"] == "invalid_record_schema")
    assert held["candidate"] == before
    if candidate in [
        {"sources": {"block_id": "b"}},
        {"content": [{"sources": {"block_id": "b", "excerpt": "Example"}}]},
    ]:
        assert held["source_contexts"][0]["block_id"] == "b"
    assert read_json(tmp_path / "audit/loader-preview.json")["nodes"] == []
    assert (tmp_path / "review.html").exists()
