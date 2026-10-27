import copy
import json

import pytest
from pypdf import PdfWriter

from document_toolkit.common import read_json, write_json
from document_toolkit.config import Settings
from document_toolkit.pipeline import extract_document
from knowledge_pipeline.pipeline import HERE, export_candidates, inventory, prepare
from knowledge_pipeline.validation import validate_extraction
from knowledge_pipeline.mapping import legacy_proposals


@pytest.fixture
def sample(tmp_path):
    folder = tmp_path / "data/raw-source"
    folder.mkdir(parents=True)
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    writer.write(folder / "book.pdf")
    book = {
        "document_edition_id": "ED_fixture",
        "source_id": "SRC_FIXTURE",
        "title": "Synthetic fixture book",
        "publication_year": 2026,
        "repo_relative_path": "data/raw-source/book.pdf",
        "trial_pdf_pages": [1, 2],
        "identity_pdf_pages": [],
        "verified_printed_labels": {"1": "x", "2": "11"},
    }
    output = tmp_path / "data/knowledge-extraction"
    inventory(tmp_path, {"documents": [book]}, output)
    text = {
        1: "Nếu có tổn thương, phải thực hiện bước A; không dùng 10 mg khi chưa kiểm tra.",
        2: "Bước B chỉ thực hiện sau bước A.",
    }
    prepared, report = prepare(
        tmp_path,
        {"documents": [book]},
        output,
        ocr_page=lambda p, n: text[n],
        ocr_metadata={"engine": "fixture_only"},
    )
    chunk = prepared[0][2][0]
    supports = [
        {"span_id": s["span_id"], "quote": s["text"]} for s in chunk["source_spans"]
    ]
    value = {
        "source_units": [
            {
                "local_id": "u",
                "title": "Synthetic contextual evidence",
                "supports": supports,
            }
        ],
        "concepts": [
            {
                "local_id": "c",
                "verbatim_name": "tổn thương",
                "proposed_name": "tổn thương",
                "concept_type": "condition",
                "aliases": [],
                "source_unit_ids": ["u"],
            }
        ],
        "statements": [
            {
                "local_id": "s",
                "statement_type": "procedure",
                "text": "\n".join(s["quote"] for s in supports),
                "quotes": [s["quote"] for s in supports],
                "source_unit_ids": ["u"],
                "concept_ids": ["c"],
                "conditions": ["Nếu có tổn thương"],
                "negations": ["không"],
                "requirements": ["phải"],
                "temporal_information": [],
                "extraction_kind": "direct",
                "interpretation": None,
                "relation": None,
                "procedure_context": "Synthetic procedure in ED_fixture",
                "sequence": [],
            }
        ],
    }
    schema = read_json(HERE / "schemas/extraction.schema.json")
    return tmp_path, output, prepared, report, chunk, value, schema


def test_page_provenance_and_review_gate(sample):
    _, output, prepared, report, chunk, value, schema = sample
    validation = validate_extraction(value, chunk, schema)
    assert validation["expert_review"] == "unverified"
    assert [s["pdf_page"] for s in chunk["source_spans"]] == [1, 2]
    assert report["documents"][0]["unprocessed_pages"] == [3]
    inv = read_json(output / "inventory.json")["documents"][0]
    assert inv["pdf_text_status"] == "scan_no_text" and inv["unreadable_pages"] == [
        1,
        2,
        3,
    ]
    raw = {
        "status": "complete",
        "failures": [],
        "results": [{"chunk_id": chunk["chunk_id"], "extraction": value}],
    }
    result = export_candidates(
        [(prepared[0][0], raw, [chunk])], output, "unit-test-fake", "test-v1", schema
    )
    assert result["counts"] == {
        "source_units": 1,
        "concept_candidates": 1,
        "medical_statements": 1,
    }
    first = (output / "runs/validated/source_units.jsonl").read_text(encoding="utf-8")
    export_candidates(
        [(prepared[0][0], raw, [chunk])], output, "unit-test-fake", "test-v1", schema
    )
    assert first == (output / "runs/validated/source_units.jsonl").read_text(
        encoding="utf-8"
    )
    row = json.loads(first)
    assert not row["usable_as_default_evidence"]
    assert [s["printed_page_label"] for s in row["supports"]] == ["x", "11"]
    assert row["course_id"] is None and row["topic_id"] is None


@pytest.mark.parametrize(
    "kind",
    [
        "quote",
        "duplicate",
        "reference",
        "number",
        "negation",
        "alias",
        "relation",
        "sequence",
    ],
)
def test_reject_invalid_candidates(sample, kind):
    *_, chunk, original, schema = sample
    value = copy.deepcopy(original)
    if kind == "quote":
        value["source_units"][0]["supports"][0]["quote"] = "unsupported source"
    if kind == "duplicate":
        value["source_units"].append(copy.deepcopy(value["source_units"][0]))
    if kind == "reference":
        value["statements"][0]["source_unit_ids"] = ["missing"]
    if kind == "number":
        value["statements"][0]["text"] = value["statements"][0]["text"].replace(
            "10", "100"
        )
    if kind == "negation":
        value["statements"][0]["text"] = value["statements"][0]["text"].replace(
            "không", ""
        )
    if kind == "alias":
        value["concepts"][0]["aliases"] = ["not in source"]
    if kind == "relation":
        value["statements"][0]["relation"] = {
            "subject_concept_id": "missing",
            "predicate": "x",
            "object_concept_id": "c",
        }
    if kind == "sequence":
        value["statements"][0].update(
            sequence=[{"position": 1, "quote": "Bước B"}], procedure_context=None
        )
    with pytest.raises(ValueError):
        validate_extraction(value, chunk, schema)


def test_unreadable_ocr_error_not_success(sample):
    root, output, prepared, *_ = sample

    def broken(_p, n):
        if n == 2:
            raise RuntimeError("fixture failure")
        return "Source page one"

    _, report = prepare(root, {"documents": [prepared[0][0]]}, output, ocr_page=broken)
    assert report["documents"][0]["unreadable_pages"] == [2]
    assert report["documents"][0]["page_errors"] == {2: "RuntimeError"}


def test_resume_and_invalidation_without_network(sample):
    _, output, prepared, _, _, value, schema = sample

    class Fake:
        calls = 0

        def chat_json(self, *args):
            self.calls += 1
            return value

    fake = Fake()
    target = output / "fixture.result.json"
    settings = Settings(llm_base_url="http://fixture.invalid", model="fake")
    kwargs = dict(
        settings=settings,
        prompt="fixture",
        schema=schema,
        client=fake,
        validator=lambda v, c: validate_extraction(v, c, schema),
        validator_version="fixture-v1",
    )
    extract_document(prepared[0][1], target, **kwargs)
    extract_document(prepared[0][1], target, resume=True, **kwargs)
    assert fake.calls == 1
    changes = [
        {"prompt": "changed"},
        {"validator_version": "changed"},
        {"max_chunk_bytes": 1000},
        {"settings": Settings(llm_base_url="http://fixture.invalid", model="other")},
        {"schema": {**schema, "title": "changed"}},
    ]
    for changed in changes:
        with pytest.raises(ValueError, match="changed"):
            extract_document(
                prepared[0][1], target, resume=True, **{**kwargs, **changed}
            )
    data = read_json(prepared[0][1])
    data["sections"][0]["text"] += " changed"
    write_json(prepared[0][1], data)
    with pytest.raises(ValueError, match="changed"):
        extract_document(prepared[0][1], target, resume=True, **kwargs)
    assert fake.calls == 1


def test_failed_validation_not_cached(sample):
    _, output, prepared, _, _, value, schema = sample

    class Bad:
        def chat_json(self, *args):
            wrong = copy.deepcopy(value)
            wrong["source_units"][0]["supports"][0]["quote"] = "unsupported"
            return wrong

    target = output / "invalid.raw.json"
    result = extract_document(
        prepared[0][1],
        target,
        settings=Settings(model="fake"),
        prompt="fixture",
        schema=schema,
        client=Bad(),
        validator=lambda v, c: validate_extraction(v, c, schema),
        validator_version="v1",
    )
    assert result["status"] == "partial" and result["completed_chunks"] == 0
    assert read_json(target.with_suffix(".checkpoint.json"))["calls"] == {}


def test_manifest_locator_priority_and_no_merge():
    candidates = [
        {
            "source_unit_id": "new",
            "source_id": "source",
            "supports": [{"pdf_page": 16, "quote": "original"}],
        }
    ]
    old = [
        {
            "source_unit_id": "old",
            "source_id": "source",
            "page_start": 17,
            "page_end": 18,
            "content": "condensed",
        }
    ]
    manifests = [
        {"source_unit_ids": ["old"], "locator": {"pdf_pages": {"start": 16, "end": 16}}}
    ]
    rows = legacy_proposals(candidates, old, manifests)
    assert (
        len(rows) == 1 and rows[0]["existing_locator_basis"] == "integration_manifest"
    )
    assert rows[0]["status"] == "needs_review" and not rows[0]["replace_existing"]
    assert old[0]["page_start"] == 17


@pytest.mark.parametrize("pages", [[], [0], [4]])
def test_toolkit_rejects_out_of_range_pages(sample, pages):
    root, *_ = sample
    from document_toolkit.documents import read_document

    with pytest.raises(ValueError):
        read_document(root / "data/raw-source/book.pdf", page_numbers=pages)


def test_toolkit_reads_only_selected_pages(sample):
    root, *_ = sample
    from document_toolkit.documents import read_document

    seen = []

    def callback(_path, n):
        seen.append(n)
        return "fixture text"

    data = read_document(
        root / "data/raw-source/book.pdf", page_numbers=[2], ocr_page=callback
    )
    assert seen == [2] and data["sections"][0]["page_start"] == 2


def test_wrapper_export_and_resume_with_injected_client(sample, monkeypatch):
    _, output, prepared, _, _, value, _ = sample
    import knowledge_pipeline.pipeline as module

    class Fake:
        calls = 0

        def chat_json(self, *_):
            self.calls += 1
            return copy.deepcopy(value)

    fake = Fake()

    def scoped_extract(*args, **kwargs):
        return extract_document(*args, client=fake, **kwargs)

    monkeypatch.setattr(module, "extract_document", scoped_extract)
    settings = Settings(
        llm_base_url="http://fixture.invalid", model="fake", llm_max_attempts=1
    )
    report = module.extract(prepared, output, settings=settings)
    assert (
        report["status"] == "complete_scope" and report["default_evidence_count"] == 0
    )
    assert report["counts"]["medical_statements"] == 1
    manifests = list((output / "runs/config").glob("*/manifest.json"))
    assert len(manifests) == 1 and "api_key" not in manifests[0].read_text(
        encoding="utf-8"
    )
    module.extract(prepared, output, settings=settings, resume=True)
    assert fake.calls == 1
    with pytest.raises(ValueError, match="changed"):
        module.extract(
            prepared,
            output,
            settings=Settings(
                llm_base_url="http://fixture.invalid",
                model="fake",
                max_output_tokens=100,
            ),
            resume=True,
        )
    assert fake.calls == 1
