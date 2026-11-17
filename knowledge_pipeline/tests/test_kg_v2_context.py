import hashlib

import pytest

from knowledge_pipeline.kg_v2.context import structure_window
from knowledge_pipeline.kg_v2.corrections import correct_page, trace_raw
from knowledge_pipeline.kg_v2.registry import approve_decisions, resolve_graph
from knowledge_pipeline.kg_v2.validation import check_edge
from knowledge_pipeline.tests.test_kg_v2 import block, compile_one, medical, support


def test_request_metrics_capacity_and_resume_without_extra_http(monkeypatch, tmp_path):
    import httpx

    from document_toolkit.common import read_json, write_json
    from document_toolkit.config import Settings
    from knowledge_pipeline.kg_v2 import pipeline

    b = {**block(), "section_title": "test"}
    prepared = {
        "windows": [{"window_id": "w", "blocks": [b]}],
        "pages": [],
        "catalog": [],
        "sections": [],
        "ocr_metadata": {},
        "preparation_rejected": [],
    }
    monkeypatch.setattr(pipeline, "prepare", lambda *args: prepared)
    requests = []

    def respond(request):
        requests.append(request)
        raw = {"nodes": [medical(b, identifier=str(i)) for i in range(12)], "edges": []}
        import json

        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(raw)}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

    monkeypatch.setattr(
        pipeline.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond)
    )
    scope = tmp_path / "scope.json"
    write_json(scope, {})
    output = tmp_path / "data/knowledge-extraction/v2/metrics"
    settings = Settings(
        llm_base_url="http://fixture.invalid/v1",
        llm_api_key="private-fixture",
        model="fake",
        prompt_budget_bytes=70000,
    )
    result = pipeline.run(scope, output, settings=settings, root=tmp_path)
    assert result["capacity_review_windows"][0]["nodes"] == 12
    metrics = read_json(output / "audit/request-metrics.json")
    assert metrics[0]["usage"]["total_tokens"] == 150
    assert metrics[0]["http_status"] == 200
    assert "private-fixture" not in (output / "audit/request-metrics.json").read_text()
    resumed = pipeline.run(scope, output, settings=settings, root=tmp_path, resume=True)
    assert resumed["cache_hits_this_run"] == 1
    assert resumed["llm_calls_this_run"] == 0 and len(requests) == 1


def test_unresolved_ocr_meaning_is_held_out():
    from knowledge_pipeline.kg_v2.validation import source_entries

    b = block("Uncertain clinical phrase requiring visual review.")
    b["unresolved_issues"] = [{"text": "Uncertain clinical phrase"}]
    with pytest.raises(ValueError, match="unresolved_ocr_affects_meaning"):
        source_entries([{"block_id": b["block_id"]}], {b["block_id"]: b}, {})


def structured(new_section=False, second_page=False, continued=False):
    text = (
        "1. Phân loại\nPhân độ fracture theo SystemA: gồm các độ:\n- Độ I: Description."
    )
    a = {**block(text), "section_id": "sec", "section_title": "Classification"}
    blocks = [a]
    if second_page:
        a["text"] = "1. Phân loại\nPhân độ fracture theo SystemA: gồm các độ:"
        blocks.append(
            {
                **block("- Độ I: Description.", identifier="b2", page=17),
                "continuation_verified": continued,
            }
        )
    if new_section:
        blocks[0]["text"] = text.replace("- Độ I", "2. Other section\n- Độ I")
    return structure_window({"window_id": "w", "blocks": blocks})


def category_edge(window, relation="HAS_CATEGORY"):
    heading = next(b for b in window["blocks"] if b["kind"] == "system_heading")
    item = next(b for b in window["blocks"] if b["kind"] == "category")
    local = {
        "c": {"id": "c", "type": "Classification", "name": "SystemA"},
        "l": {"id": "l", "type": "ClassificationCategory", "name": "Độ I"},
    }
    raw = {
        "from_id": "c",
        "to_id": "l",
        "type": relation,
        "condition": None,
        "sources": [{"block_id": heading["block_id"]}, {"block_id": item["block_id"]}],
    }
    return raw, local, {b["block_id"]: b for b in window["blocks"]}


def test_heading_and_bullet_prove_edge_without_same_quote():
    raw, local, blocks = category_edge(structured())
    edge = check_edge(raw, local, blocks, {})
    assert len(edge["sources"]) == 2
    assert "SystemA" not in edge["sources"][1]["excerpt"]


@pytest.mark.parametrize(
    "new_section,second_page,continued", [(True, False, False), (False, True, False)]
)
def test_context_stops_at_new_heading_or_unverified_page(
    new_section, second_page, continued
):
    raw, local, blocks = category_edge(structured(new_section, second_page, continued))
    with pytest.raises(ValueError, match="verified_structure"):
        check_edge(raw, local, blocks, {})


def test_page_continuation_only_when_explicitly_verified():
    raw, local, blocks = category_edge(structured(second_page=True, continued=True))
    assert check_edge(raw, local, blocks, {})["type"] == "HAS_CATEGORY"


def test_same_page_cooccurrence_does_not_prove_classification():
    b = block("SystemA mentions Độ I.")
    local = {
        "c": {"id": "c", "type": "Classification", "name": "SystemA"},
        "l": {"id": "l", "type": "ClassificationCategory", "name": "Độ I"},
    }
    raw = {
        "from_id": "c",
        "to_id": "l",
        "type": "HAS_CATEGORY",
        "condition": None,
        "sources": [support(b)],
    }
    with pytest.raises(ValueError, match="verified_structure"):
        check_edge(raw, local, {"b": b}, {})


def test_category_subtype_uses_is_a_not_has_category():
    w = structure_window(
        {
            "blocks": [
                block(
                    "Phân độ fracture theo SystemA:\n- Độ 3: Chia ra:\n+ Độ 3a: Không được bỏ điều kiện."
                )
            ]
        }
    )
    parent = next(b for b in w["blocks"] if b.get("category_code") == "3")
    child = next(b for b in w["blocks"] if b.get("category_code") == "3a")
    local = {
        "a": {"id": "a", "type": "ClassificationCategory", "name": "Độ 3a"},
        "b": {"id": "b", "type": "ClassificationCategory", "name": "Độ 3"},
    }
    raw = {
        "from_id": "a",
        "to_id": "b",
        "type": "IS_A",
        "condition": None,
        "sources": [{"block_id": parent["block_id"]}, {"block_id": child["block_id"]}],
    }
    lookup = {b["block_id"]: b for b in w["blocks"]}
    assert check_edge(raw, local, lookup, {})["type"] == "IS_A"
    with pytest.raises(ValueError, match="end_types"):
        check_edge({**raw, "type": "HAS_CATEGORY"}, local, lookup, {})


def test_confirmed_patch_traces_to_raw_and_never_changes_original(tmp_path):
    proof = tmp_path / "page.png"
    proof.write_bytes(b"unit-test-image")
    raw = "ở gãy"
    patch = {
        "id": "p",
        "source_id": "SRC",
        "pdf_page": 1,
        "raw_start": 0,
        "raw_end": len(raw),
        "before": raw,
        "after": "ổ gãy",
        "ocr_sha256": "ocr",
        "source_pdf_sha256": "pdf",
        "decision": "confirmed_visual_transcription",
        "kind": "ocr_character_or_word",
        "image_path": "page.png",
        "image_sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
    }
    correction = correct_page(
        raw,
        [patch],
        source_id="SRC",
        page=1,
        ocr_sha256="ocr",
        pdf_sha256="pdf",
        root=tmp_path,
    )
    trace = trace_raw(correction, 0, len(correction["corrected_text"]))
    assert (
        trace["raw_text"] == raw
        and trace["corrected_text"] == "ổ gãy"
        and trace["patch_ids"] == ["p"]
    )
    assert raw == "ở gãy"


@pytest.mark.parametrize("before,after", [("10 mg", "20 mg"), ("không dùng", "dùng")])
def test_patch_cannot_silently_change_numbers_or_negation(tmp_path, before, after):
    proof = tmp_path / "page.png"
    proof.write_bytes(b"image")
    patch = {
        "id": "p",
        "source_id": "s",
        "pdf_page": 1,
        "raw_start": 0,
        "raw_end": len(before),
        "before": before,
        "after": after,
        "ocr_sha256": "o",
        "source_pdf_sha256": "p",
        "decision": "confirmed_visual_transcription",
        "kind": "ocr_character_or_word",
        "image_path": "page.png",
        "image_sha256": hashlib.sha256(b"image").hexdigest(),
    }
    with pytest.raises(ValueError, match="numeric_or_negation"):
        correct_page(
            before,
            [patch],
            source_id="s",
            page=1,
            ocr_sha256="o",
            pdf_sha256="p",
            root=tmp_path,
        )


def test_title_only_node_is_not_a_description():
    b = {**block("1. Fracture"), "kind": "heading"}
    graph, audit = compile_one({"nodes": [medical(b)], "edges": []}, [b])
    assert (
        not graph["nodes"]
        and audit["rejected"][0]["reason"]
        == "title_only_content_is_not_medical_description"
    )


def entity(cid, kind="Condition", name="Fracture", source="a"):
    return {
        "id": cid,
        "type": kind,
        "name": name,
        "aliases": [],
        "content": [
            {
                "text": "Source " + source,
                "sources": [
                    {
                        "source_id": source,
                        "locator_id": "l" + source,
                        "pdf_pages": [1],
                        "printed_pages": [],
                        "excerpt": "Source " + source,
                    }
                ],
            }
        ],
    }


def test_canonical_uuid_stable_after_page_quote_change_and_explicit_resolution(
    tmp_path,
):
    path = tmp_path / "registry.json"
    a = entity("candidate-source-A")
    graph = {"schema_version": "medical-kg-v2", "nodes": [a], "edges": []}
    r = approve_decisions(
        path,
        graph,
        [
            {
                "candidate_ids": [a["id"]],
                "approved": True,
                "basis": "definition identity reviewed",
            }
        ],
    )
    canonical = r["bindings"][a["id"]]
    b = entity("different-page-window-quote", source="b")
    graph["nodes"].append(b)
    resolved, audit = resolve_graph(graph, r)
    assert len(resolved["nodes"]) == 1 and audit["pending_identity_review"]
    decision = {
        "candidate_ids": [b["id"]],
        "existing_id": canonical,
        "approved": True,
        "basis": "same meaning and type after source review",
    }
    r = approve_decisions(path, graph, [decision])
    r = approve_decisions(path, graph, [decision])
    resolved, _ = resolve_graph(graph, r)
    assert (
        resolved["nodes"][0]["id"] == canonical
        and len(resolved["nodes"][0]["content"]) == 2
    )
    assert len(r["entities"]) == 1


def test_level_i_in_two_systems_never_merges(tmp_path):
    path = tmp_path / "registry.json"
    nodes = [
        entity("s"),
        entity("A", "Classification", "SystemA"),
        entity("B", "Classification", "SystemB"),
        entity("a", "ClassificationCategory", "Độ I"),
        entity("b", "ClassificationCategory", "Độ I"),
    ]
    graph = {"schema_version": "medical-kg-v2", "nodes": nodes, "edges": []}
    decisions = [
        {
            "candidate_ids": [n["id"]],
            "approved": True,
            "basis": "source structure checked",
        }
        for n in nodes
    ]
    decisions[3]["context"] = {
        "system_candidate_id": "A",
        "subject_candidate_id": "s",
        "level": "Độ I",
    }
    decisions[4]["context"] = {
        "system_candidate_id": "B",
        "subject_candidate_id": "s",
        "level": "Độ I",
    }
    r = approve_decisions(path, graph, decisions)
    resolved, _ = resolve_graph(graph, r)
    names = [
        n["name"] for n in resolved["nodes"] if n["type"] == "ClassificationCategory"
    ]
    assert len(set(names)) == 2 and all("System" in n for n in names)
    graph["nodes"].append(entity("new-b", "ClassificationCategory", "Độ I"))
    with pytest.raises(ValueError, match="must_not_merge"):
        approve_decisions(
            path,
            graph,
            [
                {
                    **decisions[4],
                    "candidate_ids": ["new-b"],
                    "existing_id": r["bindings"]["a"],
                }
            ],
        )


def test_model_missing_child_quote_is_retrieved_only_from_exact_list():
    from knowledge_pipeline.kg_v2.context import normalize_edge_context

    raw, local, blocks = category_edge(structured())
    raw["local_id"] = "e"
    raw["sources"] = raw["sources"][:1]
    normalized_edge, events = normalize_edge_context(raw, local, blocks)
    assert len(normalized_edge["sources"]) == 2 and events
    assert check_edge(normalized_edge, local, blocks, {})["type"] == "HAS_CATEGORY"
    raw, local, unrelated = category_edge(structured(new_section=True))
    raw["local_id"] = "e"
    raw["sources"] = raw["sources"][:1]
    normalized_edge, _ = normalize_edge_context(raw, local, unrelated)
    assert len(normalized_edge["sources"]) == 1


def test_classification_title_retrieves_actual_bullets_not_knowledge():
    from knowledge_pipeline.kg_v2.context import expand_node_content

    window = structured()
    lookup = {b["block_id"]: b for b in window["blocks"]}
    heading = next(b for b in lookup.values() if b["kind"] == "system_heading")
    raw = medical(heading, name="SystemA", kind="Classification")
    expanded, events = expand_node_content(raw, lookup)
    assert len(expanded["content"][0]["sources"]) == 2 and events
    assert raw["content"] != expanded["content"]


def test_intervention_is_not_the_skill_and_edges_are_remapped(tmp_path):
    from knowledge_pipeline.kg_v2.loader import dry_run_loader

    path = tmp_path / "registry.json"
    intervention = entity("i", "Intervention", "Method")
    skill = entity("s", "Skill", "Perform method")
    skill.pop("aliases")
    skill["kind"] = "practical"
    edge = {
        "id": "e",
        "from_id": "s",
        "to_id": "i",
        "type": "APPLIES_TO",
        "condition": None,
        "sources": intervention["content"][0]["sources"],
    }
    graph = {
        "schema_version": "medical-kg-v2",
        "nodes": [intervention, skill],
        "edges": [edge],
    }
    r = approve_decisions(
        path,
        graph,
        [
            {
                "candidate_ids": [n["id"]],
                "approved": True,
                "basis": "explicit procedure and skill evidence",
            }
            for n in graph["nodes"]
        ],
    )
    resolved, _ = resolve_graph(graph, r)
    assert resolved["edges"][0]["from_id"] == r["bindings"]["s"]
    assert resolved["edges"][0]["to_id"] == r["bindings"]["i"]
    assert len(dry_run_loader(resolved)["nodes"]) == 2
    with pytest.raises(ValueError, match="same_type"):
        approve_decisions(
            path,
            graph,
            [{"candidate_ids": ["s", "i"], "approved": True, "basis": "invalid merge"}],
        )
