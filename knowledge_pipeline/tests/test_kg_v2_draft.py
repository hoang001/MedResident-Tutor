import json

import httpx
import pytest

from document_toolkit.common import read_json, write_json
from document_toolkit.config import Settings
from document_toolkit.llm_client import LLMError
from knowledge_pipeline.kg_v2 import pipeline
from knowledge_pipeline.kg_v2.draft import resolve_draft
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.registry import approve_decisions, load_registry
from knowledge_pipeline.kg_v2.transport import (
    BudgetedLLM,
    BudgetExhausted,
    RequestBudget,
)
from knowledge_pipeline.kg_v2.validation import source_entries, supported_node
from knowledge_pipeline.tests.test_kg_v2 import block, medical, support


def compile_draft(nodes, blocks, edges=()):
    return pipeline.compile_graph(
        {"w": {"nodes": nodes, "edges": list(edges)}},
        [{"window_id": "w", "blocks": blocks}],
        draft=True,
    )


def test_bad_alias_only_is_removed_and_independent_edges_survive():
    b = block("Fracture ở bone.")
    c, a = medical(b), medical(b, "a", "bone", "Anatomy")
    c["aliases"] = ["Unsupported synonym"]
    edge = {
        "local_id": "e",
        "from_id": "c",
        "to_id": "a",
        "type": "LOCATED_IN",
        "condition": None,
        "sources": [support(b)],
    }
    graph, audit = compile_draft([c, a], [b], [edge])
    assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 1
    assert next(n for n in graph["nodes"] if n["type"] == "Condition")["aliases"] == []
    assert any(
        r["reason"] == "removed_unsupported_alias" for r in audit["review_items"]
    )
    assert not audit["rejected"]
    dry_run_loader(graph)


def test_qualifier_guard_stops_at_quote_sentence_end_and_still_protects_same_sentence():
    b = block("Fracture is a condition. Do not use 10 mg unless checked.")
    source_entries(
        [{"block_id": "b", "excerpt": "Fracture is a condition."}],
        {"b": b},
        {},
        preserve_qualifiers=True,
    )
    with pytest.raises(ValueError, match="omits_condition"):
        source_entries(
            [{"block_id": "b", "excerpt": "use 10 mg"}],
            {"b": b},
            {},
            preserve_qualifiers=True,
        )


def test_inline_heading_has_real_content_and_van_dung_is_a_skill_action():
    b = {
        **block("7.1.3. Bất động: bất động bằng băng Desault để 3-4 tuần."),
        "kind": "heading",
    }
    node, _ = supported_node(
        medical(b, name="Desault", kind="Intervention"), {"b": b}, {}
    )
    assert "3-4 tuần" in node["content"][0]["text"]
    obj = block("Vận dụng được nguyên tắc điều trị Fracture.", "learning_objective")
    skill = {
        "local_id": "s",
        "type": "Skill",
        "name": "Vận dụng nguyên tắc điều trị Fracture",
        "kind": "cognitive",
        "basis": "learning_objective",
        "basis_sources": [support(obj)],
        "identity_sources": [support(obj)],
        "content": [{"sources": [support(obj)]}],
    }
    node, _ = supported_node(skill, {"b": obj}, {})
    assert node["type"] == "Skill"


def test_cited_block_restoration_keeps_monitoring_without_inventing_an_edge():
    b = block("Fracture is reduced gently. Always check stability after reduction.")
    row = medical(b)
    row["content"][0]["sources"][0]["excerpt"] = "Fracture is reduced gently."
    graph, audit = compile_draft([row], [b])
    assert graph["nodes"][0]["content"][0]["text"] == b["text"]
    assert not graph["edges"]
    assert any(
        r["reason"] == "restored_whole_cited_block" for r in audit["review_items"]
    )


def test_uncertain_sourced_edge_is_reviewable_but_invalid_direction_is_not_reversed():
    b = block("Fracture không gây swelling. Reduction is a method.")
    nodes = [
        medical(b),
        medical(b, "f", "swelling", "Finding"),
        medical(b, "i", "Reduction", "Intervention"),
    ]
    edges = [
        {
            "local_id": "e",
            "from_id": "c",
            "to_id": "f",
            "type": "HAS_FINDING",
            "condition": None,
            "sources": [support(b)],
        },
        {
            "local_id": "bad",
            "from_id": "i",
            "to_id": "c",
            "type": "MANAGED_BY",
            "condition": None,
            "sources": [support(b)],
        },
    ]
    graph, audit = compile_draft(nodes, [b], edges)
    assert len(graph["edges"]) == 1 and graph["edges"][0]["type"] == "HAS_FINDING"
    assert any(
        r["reason"] == "negative_edge_requires_manual_review"
        for r in audit["review_items"]
    )
    held = next(
        r
        for r in audit["review_items"]
        if r["reason"] == "invalid_relationship_end_types_no_auto_reversal"
    )
    assert held["candidate"]["from_id"] == "i"


def test_bad_locator_and_ocr_hold_do_not_remove_independent_node():
    good, bad = block(), block("Unknown corrupted meaning.", identifier="bad")
    bad["unresolved_issues"] = [{"text": "Unknown corrupted"}]
    broken = medical(good, "unknown")
    broken["identity_sources"] = [{"block_id": "missing"}]
    graph, audit = compile_draft(
        [medical(good), medical(bad, "bad", "Unknown"), broken], [good, bad]
    )
    assert len(graph["nodes"]) == 1
    assert {r["reason"] for r in audit["rejected"]} == {
        "unknown_block",
        "unresolved_ocr_affects_meaning",
    }


def test_draft_ids_persist_and_later_confirmed_merge_remaps_without_mutating_canonical(
    tmp_path,
):
    b = block()
    graph, _ = compile_draft([medical(b)], [b])
    registry = tmp_path / "canonical.json"
    path = tmp_path / "draft.json"
    first, _ = resolve_draft(graph, load_registry(registry), path)
    second, _ = resolve_draft(graph, load_registry(registry), path)
    assert first == second and first["nodes"][0]["id"].startswith("DRN_")
    approved = approve_decisions(
        registry,
        graph,
        [
            {
                "candidate_ids": [graph["nodes"][0]["id"]],
                "approved": True,
                "basis": "test reviewed identity",
            }
        ],
    )
    raw_registry = registry.read_bytes()
    mapped, audit = resolve_draft(graph, approved, path)
    assert mapped["nodes"][0]["id"].startswith("MC_")
    assert audit["draft_id_migrations"][0]["old_id"] == first["nodes"][0]["id"]
    assert registry.read_bytes() == raw_registry


def test_same_name_different_source_is_not_merged(tmp_path):
    b = block()
    other = {**block(identifier="other"), "source_id": "OTHER"}
    graph, _ = compile_draft([medical(b), medical(other, "second")], [b, other])
    resolved, _ = resolve_draft(
        graph, {"bindings": {}, "entities": {}}, tmp_path / "ids.json"
    )
    assert len({n["id"] for n in resolved["nodes"]}) == 2


def test_question_is_restored_from_real_source_and_invented_answer_removed():
    b = block("Question one?\nA. First\nB. Second", "question")
    q = {
        "local_id": "q",
        "type": "SampleQuestion",
        "text": "Question one?",
        "format": "multiple_choice",
        "options": ["First"],
        "answer": "First",
        "explanation": "Invented",
        "sources": [{"block_id": "b", "excerpt": "Question one?"}],
        "answer_sources": [],
    }
    graph, audit = compile_draft([q], [b])
    node = graph["nodes"][0]
    assert node["text"] == b["text"] and node["options"] == ["First", "Second"]
    assert node["answer"] is None and node["explanation"] is None
    assert any(
        r["reason"] == "removed_unsupported_answer" for r in audit["review_items"]
    )


def settings():
    return Settings(
        llm_base_url="http://fixture.invalid/v1",
        llm_api_key="private-fixture",
        model="fake",
        prompt_budget_bytes=70000,
        llm_max_attempts=1,
    )


@pytest.mark.parametrize(
    "error,category",
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")],
)
def test_transport_cause_latency_and_budget_are_safe(error, category):
    def respond(request):
        raise error("private-fixture must not be logged", request=request)

    budget = RequestBudget(1, 10)
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = BudgetedLLM(settings(), http, budget, lambda rows: None)
        with pytest.raises(LLMError) as caught:
            client.chat_json("fake", [{"role": "user", "content": "test"}])
        assert caught.value.diagnostics["category"] == category
        assert "latency_seconds" in caught.value.diagnostics
        assert "private-fixture" not in json.dumps(caught.value.diagnostics)
        with pytest.raises(BudgetExhausted):
            client.chat_json("fake", [{"role": "user", "content": "test"}])
    assert budget.calls == 1


def test_auth_error_blocks_further_requests_and_parse_is_not_retryable():
    budget = RequestBudget(3, 10)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                401, json={"error": {"type": "auth", "message": "private-fixture"}}
            )
        )
    ) as http:
        client = BudgetedLLM(settings(), http, budget, lambda rows: None)
        with pytest.raises(LLMError) as caught:
            client.chat_json("fake", [{"role": "user", "content": "test"}])
        assert caught.value.diagnostics["category"] == "authentication"
        assert "private-fixture" not in json.dumps(caught.value.diagnostics)
        with pytest.raises(BudgetExhausted):
            client.chat_json("fake", [{"role": "user", "content": "test"}])


@pytest.mark.parametrize("content,category", [("not JSON", "parse"), ("[]", "schema")])
def test_parse_and_schema_errors_are_not_transport_retries(content, category):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": content}, "finish_reason": "stop"}
                    ]
                },
            )
        )
    ) as http:
        client = BudgetedLLM(settings(), http, RequestBudget(2, 10), lambda rows: None)
        with pytest.raises(LLMError) as caught:
            client.chat_json(
                "fake", [{"role": "user", "content": "test"}], {"type": "object"}
            )
        assert caught.value.diagnostics["category"] == category
        assert not caught.value.diagnostics["retryable"]


def prepared(scope, *args):
    b = {**block(), "section_title": "test", "kind": "body"}
    return {
        "windows": [{"window_id": w, "blocks": [b]} for w in scope["ids"]],
        "pages": [],
        "catalog": [],
        "sections": [],
        "ocr_metadata": {},
        "preparation_rejected": [],
    }


def successful_response(request):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"nodes": [medical(block())], "edges": []}
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 10},
        },
    )


def test_retry_uses_allowance_and_resume_uses_cache_when_quota_changes(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(pipeline, "prepare", prepared)
    calls = []

    def respond(request):
        calls.append(request)
        return (
            httpx.Response(429, json={"error": {"type": "rate_limit"}})
            if len(calls) == 1
            else successful_response(request)
        )

    monkeypatch.setattr(
        pipeline.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond)
    )
    scope = tmp_path / "scope.json"
    write_json(scope, {"ids": ["w1", "w2"]})
    output = tmp_path / "data/knowledge-extraction/v2/draft"
    options = {
        "draft": True,
        "settings": settings(),
        "root": tmp_path,
        "draft_registry_path": tmp_path / "ids.json",
    }
    first = pipeline.run(scope, output, max_calls=2, **options)
    assert len(calls) == 2 and first["windows_with_raw_output"] == 1
    second = pipeline.run(scope, output, max_calls=1, resume=True, **options)
    assert len(calls) == 3 and second["cache_hits_this_run"] == 1
    assert second["windows_with_raw_output"] == 2
    assert (output / "review.html").exists()
    dry_run_loader(read_json(output / "graph.json"))


def test_batch_budget_is_shared_across_shards_and_resume_is_sequential(
    monkeypatch, tmp_path
):
    from knowledge_pipeline.kg_v2.batch import run_batch

    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "prepare", prepared)
    from knowledge_pipeline.kg_v2 import draft_run

    monkeypatch.setattr(draft_run.Settings, "from_env", lambda: settings())
    calls = []

    def respond(request):
        calls.append(request)
        return successful_response(request)

    monkeypatch.setattr(
        pipeline.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond)
    )
    write_json(tmp_path / "s1.json", {"ids": ["a", "b"]})
    write_json(tmp_path / "s2.json", {"ids": ["c"]})
    plan = tmp_path / "plan.json"
    write_json(
        plan,
        {
            "shards": [
                {"key": "one", "scope": "s1.json"},
                {"key": "two", "scope": "s2.json"},
            ]
        },
    )
    output = tmp_path / "data/knowledge-extraction/v2/batch"
    first = run_batch(
        plan,
        output,
        max_calls=1,
        total_seconds=30,
        draft_registry_path=tmp_path / "ids.json",
    )
    assert len(calls) == 1 and first["shards_started"] == 1
    second = run_batch(
        plan,
        output,
        max_calls=2,
        total_seconds=30,
        resume=True,
        draft_registry_path=tmp_path / "ids.json",
    )
    assert len(calls) == 3 and second["shards_started"] == 2
    state = read_json(output / "batch-state.json")
    assert len(state["invocations"]) == 2
    assert (tmp_path / state["latest_aggregate"] / "review.html").exists()
