import copy
import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from document_toolkit.common import write_json
from document_toolkit.config import Settings
from knowledge_pipeline.kg_v2.contracts import schemas
from knowledge_pipeline.kg_v2.loader import decode_properties, dry_run_loader
from knowledge_pipeline.kg_v2.pipeline import compile_graph
from knowledge_pipeline.kg_v2.validation import (
    check_edge,
    cycle_if_added,
)


def block(
    text="Fracture is a type of condition.",
    role="medical_text",
    identifier="b",
    page=16,
):
    return {
        "block_id": identifier,
        "text": text,
        "role": role,
        "source_id": "SRC_TEST",
        "document_edition_id": "ED_TEST",
        "source_sha256": "0" * 64,
        "ocr_sha256": "1" * 64,
        "pdf_page": page,
        "printed_page_label": None,
        "char_start": 0,
        "char_end": len(text),
    }


def support(b):
    return {"block_id": b["block_id"], "excerpt": b["text"]}


def medical(b, identifier="c", name="Fracture", kind="Condition"):
    return {
        "local_id": identifier,
        "type": kind,
        "name": name,
        "aliases": [],
        "identity_sources": [support(b)],
        "content": [{"sources": [support(b)]}],
    }


def compile_one(raw, blocks):
    Draft202012Validator(schemas()[0]).validate(raw)
    return compile_graph({"w": raw}, [{"window_id": "w", "blocks": blocks}])


def test_exact_quotes_cross_pages_and_unknown_printed_labels():
    a, b = block(), block("Do not use 10 mg unless checked.", identifier="b2", page=17)
    node = medical(a)
    node["content"] = [{"sources": [support(a), support(b)]}]
    graph, audit = compile_one({"nodes": [node], "edges": []}, [a, b])
    sources = graph["nodes"][0]["content"][0]["sources"]
    assert [s["pdf_pages"] for s in sources] == [[16], [17]]
    assert all(s["printed_pages"] == [] for s in sources)
    assert len(audit["locators"]) == 2
    node["content"][0]["sources"][1]["excerpt"] = "Use 10 mg."
    graph, audit = compile_one({"nodes": [node], "edges": []}, [a, b])
    assert not graph["nodes"] and audit["rejected"][0]["reason"] == "quote_not_found"


def test_dedup_anchored_overlap_but_not_name_only():
    b = block()
    raw = {"nodes": [medical(b)], "edges": []}
    windows = [{"window_id": w, "blocks": [b]} for w in ("a", "b")]
    graph, _ = compile_graph({"a": raw, "b": raw}, windows)
    assert len(graph["nodes"]) == 1
    other = {**b, "source_id": "SRC_OTHER", "ocr_sha256": "2" * 64}
    windows[1]["blocks"] = [other]
    graph, audit = compile_graph({"a": raw, "b": raw}, windows)
    assert len(graph["nodes"]) == 2 and len(audit["merge_proposals"]) == 1
    assert not audit["merge_proposals"][0]["auto_merge"]


def test_skill_requires_explicit_basis_and_theory_is_not_practical():
    b = block("Giải thích cơ chế gãy xương hở.", role="learning_objective")
    raw = {
        "local_id": "s",
        "type": "Skill",
        "name": "Giải thích cơ chế gãy xương hở",
        "kind": "cognitive",
        "basis": "learning_objective",
        "basis_sources": [support(b)],
        "identity_sources": [support(b)],
        "content": [{"sources": [support(b)]}],
    }
    graph, _ = compile_one({"nodes": [raw], "edges": []}, [b])
    assert graph["nodes"][0]["kind"] == "cognitive"
    raw["kind"] = "practical"
    graph, audit = compile_one({"nodes": [raw], "edges": []}, [b])
    assert not graph["nodes"] and "practical" in audit["rejected"][0]["reason"]
    raw["kind"] = "cognitive"
    graph, audit = compile_one(
        {"nodes": [raw], "edges": []}, [{**b, "role": "medical_text"}]
    )
    assert (
        not graph["nodes"]
        and audit["rejected"][0]["reason"] == "skill_has_no_explicit_basis"
    )


def test_verbatim_fragment_cannot_omit_negation_and_condition():
    b = block("Fracture. Không dùng 10 mg nếu chưa kiểm tra.")
    node = medical(b)
    node["content"][0]["sources"][0]["excerpt"] = "dùng 10 mg"
    graph, audit = compile_one({"nodes": [node], "edges": []}, [b])
    assert not graph["nodes"]
    assert (
        audit["rejected"][0]["reason"]
        == "quote_omits_condition_negation_or_numeric_context"
    )


def test_real_book_question_without_answer_and_no_generated_answers():
    b = block("Explain fracture?", role="question")
    q = {
        "local_id": "q",
        "type": "SampleQuestion",
        "text": b["text"],
        "format": "open_ended",
        "options": [],
        "answer": None,
        "explanation": None,
        "sources": [support(b)],
        "answer_sources": [],
    }
    graph, _ = compile_one({"nodes": [q], "edges": []}, [b])
    assert graph["nodes"][0]["answer"] is None
    payload = dry_run_loader(graph)
    assert "answer" not in payload["nodes"][0]["properties"]
    assert (
        decode_properties(payload["nodes"][0]["properties"], "SampleQuestion")
        == graph["nodes"][0]
    )
    q["answer"] = "Invented answer"
    graph, audit = compile_one({"nodes": [q], "edges": []}, [b])
    assert not graph["nodes"] and audit["rejected"][0]["reason"] == "invented_answer"
    q["answer"] = None
    graph, audit = compile_one(
        {"nodes": [q], "edges": []}, [{**b, "role": "medical_text"}]
    )
    assert audit["rejected"][0]["reason"] == "question_not_in_book"


@pytest.mark.parametrize(
    "text,condition,reason",
    [
        ("Fracture không gây Infection.", None, "negative_edge"),
        ("Fracture gây Infection nếu untreated.", None, "loses_condition"),
        ("Fracture gây Infection.", "invented condition", "condition_not_in_source"),
    ],
)
def test_negative_or_conditional_edges_are_not_unconditional_facts(
    text, condition, reason
):
    b = block(text)
    local = {
        "a": {"id": "a", "type": "Condition", "name": "Fracture"},
        "b": {"id": "b", "type": "Condition", "name": "Infection"},
    }
    e = {
        "type": "MAY_CAUSE",
        "from_id": "a",
        "to_id": "b",
        "condition": condition,
        "sources": [support(b)],
    }
    with pytest.raises(ValueError, match=reason):
        check_edge(e, local, {"b": b}, {})


def test_edge_conditions_have_distinct_ids_and_own_evidence():
    b = block("Fracture gây Infection nếu untreated. Fracture gây Infection khi dirty.")
    local = {
        "a": {"id": "a", "type": "Condition", "name": "Fracture"},
        "b": {"id": "b", "type": "Condition", "name": "Infection"},
    }
    base = {"type": "MAY_CAUSE", "from_id": "a", "to_id": "b", "sources": [support(b)]}
    a = check_edge({**base, "condition": "nếu untreated"}, local, {"b": b}, {})
    c = check_edge({**base, "condition": "khi dirty"}, local, {"b": b}, {})
    assert a["id"] != c["id"]
    local["b"]["type"] = "Drug"
    with pytest.raises(ValueError, match="end_types"):
        check_edge({**base, "condition": "nếu untreated"}, local, {"b": b}, {})


def test_hierarchy_cycle_and_loader_rejects_provenance_labels():
    edges = [{"type": "IS_A", "from_id": "a", "to_id": "b"}]
    assert cycle_if_added(edges, {"type": "IS_A", "from_id": "b", "to_id": "a"})
    b = block()
    graph, _ = compile_one({"nodes": [medical(b)], "edges": []}, [b])
    payload = dry_run_loader(graph)
    assert payload["nodes"][0]["labels"] == ["MedicalConcept", "Condition"]
    assert (
        decode_properties(payload["nodes"][0]["properties"], "Condition")
        == graph["nodes"][0]
    )
    assert payload["neo4j_imported"] is False
    graph["nodes"][0]["type"] = "Book"
    with pytest.raises(ValidationError):
        dry_run_loader(graph)


def test_v2_resume_has_no_network_and_changed_model_does_not_overwrite(
    monkeypatch, tmp_path
):
    from knowledge_pipeline.kg_v2 import pipeline

    b = block()
    prepared = {
        "windows": [
            {
                "window_id": "w",
                "key": "test",
                "blocks": [{**b, "section_title": "test"}],
            }
        ],
        "pages": [],
        "catalog": [],
        "sections": [],
        "ocr_metadata": {},
        "preparation_rejected": [],
    }
    monkeypatch.setattr(pipeline, "prepare", lambda *args: copy.deepcopy(prepared))
    scope = tmp_path / "scope.json"
    write_json(scope, {})
    output = tmp_path / "data/knowledge-extraction/v2/test"

    class Fake:
        calls = 0

        def chat_json(self, *args):
            self.calls += 1
            return {"nodes": [medical(b)], "edges": []}

    fake = Fake()
    settings = Settings(llm_base_url="http://fixture.invalid/v1", model="fake")
    initial = pipeline.run(scope, output, settings=settings, client=fake, root=tmp_path)
    assert initial["cache_hits_this_run"] == 0
    original = (output / "graph.json").read_bytes()
    resumed = pipeline.run(
        scope, output, settings=settings, client=fake, root=tmp_path, resume=True
    )
    assert resumed["cache_hits_this_run"] == 1
    assert resumed["llm_calls_this_run"] == 0
    assert fake.calls == 1 and original == (output / "graph.json").read_bytes()
    with pytest.raises(ValueError, match="changed"):
        pipeline.run(
            scope,
            output,
            settings=Settings(
                llm_base_url="http://fixture.invalid/v1", model="changed"
            ),
            client=fake,
            root=tmp_path,
            resume=True,
        )
    assert fake.calls == 1 and original == (output / "graph.json").read_bytes()
    assert "api_key" not in (output / "audit/manifest.json").read_text()


def test_compound_question_and_all_options_are_preserved():
    b = block("Case context.\nWhich finding?\nA. Pain\nB. Swelling", role="question")
    q = {
        "local_id": "q",
        "type": "SampleQuestion",
        "text": b["text"],
        "format": "multiple_choice",
        "options": ["Pain", "Swelling"],
        "answer": None,
        "explanation": None,
        "sources": [support(b)],
        "answer_sources": [],
    }
    graph, _ = compile_one({"nodes": [q], "edges": []}, [b])
    assert graph["nodes"][0]["options"] == ["Pain", "Swelling"]
    q["options"] = ["Pain"]
    graph, audit = compile_one({"nodes": [q], "edges": []}, [b])
    assert (
        not graph["nodes"]
        and audit["rejected"][0]["reason"] == "question_options_omitted_or_changed"
    )
    q["text"] = "Which finding?"
    q["sources"][0]["excerpt"] = "Which finding?"
    _, audit = compile_one({"nodes": [q], "edges": []}, [b])
    assert audit["rejected"][0]["reason"] == "question_context_or_subparts_omitted"


def test_question_answer_on_a_different_page_retains_separate_sources():
    a = block("Explain fracture?", role="question")
    b = block("Book answer.", role="answer", identifier="answer", page=20)
    q = {
        "local_id": "q",
        "type": "SampleQuestion",
        "text": a["text"],
        "format": "open_ended",
        "options": [],
        "answer": "Book answer.",
        "explanation": None,
        "sources": [support(a)],
        "answer_sources": [support(b)],
    }
    graph, _ = compile_one({"nodes": [q], "edges": []}, [a, b])
    assert graph["nodes"][0]["sources"][0]["pdf_pages"] == [16]
    assert graph["nodes"][0]["answer_sources"][0]["pdf_pages"] == [20]


def test_aliases_are_not_assumed_from_cooccurrence_or_parentheses():
    b = block("Fracture (Infection).")
    node = medical(b)
    node["aliases"] = ["Infection"]
    graph, audit = compile_one({"nodes": [node], "edges": []}, [b])
    assert (
        not graph["nodes"]
        and audit["rejected"][0]["reason"] == "alias_equivalence_not_supported"
    )


def test_own_edge_evidence_and_neo4j_round_trip_without_driver(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "neo4j", None)
    b = block("Fracture ở bone.")
    raw = {
        "nodes": [medical(b), medical(b, "a", "bone", "Anatomy")],
        "edges": [
            {
                "local_id": "e",
                "from_id": "c",
                "to_id": "a",
                "type": "LOCATED_IN",
                "condition": None,
                "sources": [support(b)],
            }
        ],
    }
    graph, _ = compile_one(raw, [b])
    assert len(graph["edges"]) == 1
    preview = dry_run_loader(graph)
    assert (
        json.loads(preview["edges"][0]["properties"]["sources"])
        == graph["edges"][0]["sources"]
    )
    graph["nodes"][0]["status"] = "approved"
    with pytest.raises(ValidationError):
        dry_run_loader(graph)


def test_prepare_does_not_split_compound_questions_or_flatten_tables(tmp_path):
    import hashlib

    from pypdf import PdfWriter

    from knowledge_pipeline.kg_v2.pipeline import prepare

    pdf = tmp_path / "book.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    ocr = tmp_path / "data/graduate/book.json"
    write_json(
        ocr,
        {
            "source_sha256": sha,
            "page_count": 1,
            "sections": [
                {
                    "page_start": 1,
                    "page_end": 1,
                    "text": "Question context and subparts. " * 20,
                    "html": "<table><tr><td>10 mg</td><td>if needed</td></tr></table>",
                }
            ],
        },
    )
    scope = {
        "documents": [
            {
                "source_id": "SRC",
                "document_edition_id": "ED",
                "repo_relative_path": "book.pdf",
                "expected_sha256": sha,
                "windows": [
                    {
                        "key": "q",
                        "title": "Question",
                        "section_id": "sec",
                        "selectors": [{"pdf_page": 1, "role": "question"}],
                    }
                ],
            }
        ]
    }
    prepared = prepare(scope, tmp_path, max_window_bytes=100)
    assert not prepared["windows"] and prepared["preparation_rejected"]
    scope["documents"][0]["windows"][0]["selectors"][0]["role"] = "table"
    prepared = prepare(scope, tmp_path)
    assert len(prepared["windows"]) == 1
    assert prepared["windows"][0]["blocks"][0]["table_html"].startswith("<table>")


def test_offline_revalidation_refuses_an_old_schema_without_creating_output(
    tmp_path, monkeypatch
):
    import importlib

    module = importlib.import_module("knowledge_pipeline.kg_v2.revalidate")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    source = tmp_path / "data/knowledge-extraction/v2/old"
    target = tmp_path / "data/knowledge-extraction/v2/new"
    write_json(source / "audit/extraction.schema.json", {"old": "v1"})
    with pytest.raises(ValueError, match="no_automatic_migration"):
        module.revalidate(source, target)
    assert not target.exists()
