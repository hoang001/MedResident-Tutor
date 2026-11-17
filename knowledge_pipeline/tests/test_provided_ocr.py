import hashlib
import json

import pytest
from pypdf import PdfWriter

from knowledge_pipeline.ocr import provided_ocr_json


@pytest.fixture
def supplied(tmp_path):
    pdf = tmp_path / "book.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    folder = tmp_path / "data/graduate"
    folder.mkdir(parents=True)
    data = {"source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "page_count": 2, "model": "test-ocr", "status": "complete",
            "sections": [{"page_start": 1, "page_end": 1,
                          "text": "Existing OCR text; keep numbers 10 mg."}]}
    artifact = folder / "book.json"
    artifact.write_text(json.dumps(data), encoding="utf-8")
    book = {"repo_relative_path": "book.pdf", "document_edition_id": "ED_test"}
    return tmp_path, pdf, folder, artifact, book, data


def test_existing_ocr_is_verbatim_and_hash_bound(supplied):
    root, pdf, folder, artifact, book, data = supplied
    original = artifact.read_bytes()
    callback, metadata = provided_ocr_json(root, [book], folder)
    assert callback(pdf, 1) == data["sections"][0]["text"]
    assert metadata["new_ocr_calls"] == 0
    assert metadata["artifacts"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert artifact.read_bytes() == original
    with pytest.raises(ValueError, match="absent"):
        callback(pdf, 2)


@pytest.mark.parametrize("error", ["hash", "page_count", "duplicate", "zero_page"])
def test_reject_mismatched_or_ambiguous_ocr(supplied, error):
    root, _, folder, artifact, book, data = supplied
    if error == "hash":
        data["source_sha256"] = "0" * 64
    elif error == "page_count":
        data["page_count"] = 3
    elif error == "duplicate":
        data["sections"].append(data["sections"][0].copy())
    else:
        data["sections"][0]["page_start"] = 0
    artifact.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        provided_ocr_json(root, [book], folder)
