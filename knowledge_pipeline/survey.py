"""Reproducible source-only probes and section map, never LLM medical output."""

import json

from document_toolkit.common import fingerprint, write_json, read_json
from jsonschema import Draft202012Validator

from .pipeline import HERE, jsonl
from .validation import normalized


def export_survey(config, output):
    sections, probes = [], []
    for book in config["documents"]:
        edition = book["document_edition_id"]
        rows = [
            json.loads(line)
            for line in (output / "raw" / f"{edition}.pages.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        pages = {r["pdf_page"]: r for r in rows}
        section_ids = {
            s["key"]: "SEC_"
            + fingerprint([edition, s["key"], s["original_title"], s["pdf_pages"]])[:24]
            for s in book.get("survey_sections", [])
        }
        for s in book.get("survey_sections", []):
            parent = section_ids[s["parent_key"]] if s["parent_key"] else None
            sections.append(
                {
                    "document_section_id": section_ids[s["key"]],
                    "document_edition_id": edition,
                    "source_sha256": rows[0]["source_sha256"],
                    "original_title": s["original_title"],
                    "parent_section_id": parent,
                    "pdf_pages": s["pdf_pages"],
                    "printed_pages": s.get("printed_pages"),
                    "boundary_status": s["boundary_status"],
                    "basis": "visual_pdf_inspection",
                    "course_id": None,
                    "topic_id": None,
                    "expert_review": "unverified",
                }
            )
        for probe in book.get("source_probes", []):
            supports = []
            for selector in probe["selectors"]:
                row = pages[selector["pdf_page"]]
                text = row["text"]
                start = text.index(selector["start_anchor"])
                end = (
                    text.index(selector["end_anchor"], start)
                    if selector.get("end_anchor")
                    else len(text)
                )
                quote = text[start:end]
                supports.append(
                    {
                        "span_id": row["span_id"],
                        "pdf_page": row["pdf_page"],
                        "printed_page_label": row["printed_page_label"],
                        "char_start": start,
                        "char_end": end,
                        "quote": quote,
                        "normalized_quote": normalized(quote),
                    }
                )
            probes.append(
                {
                    "probe_id": "PROBE_" + fingerprint([edition, supports])[:24],
                    "document_edition_id": edition,
                    "source_id": book["source_id"],
                    "source_sha256": rows[0]["source_sha256"],
                    "probe_kind": probe["kind"],
                    "supports": supports,
                    "origin": "manual_source_selection_not_llm_extraction",
                    "status": "needs_review",
                    "expert_review": "unverified",
                    "usable_as_default_evidence": False,
                }
            )
    validator = Draft202012Validator(read_json(HERE / "schemas/records.schema.json"))
    ids = {s["document_section_id"] for s in sections}
    for s in sections:
        validator.validate(s)
        if s["parent_section_id"] and s["parent_section_id"] not in ids:
            raise ValueError("Dangling section parent")
        if not 1 <= s["pdf_pages"]["start"] <= s["pdf_pages"]["end"]:
            raise ValueError("Invalid section range")
    jsonl(output / "document_sections.jsonl", sections)
    jsonl(output / "source_probes.jsonl", probes)
    from .mapping import legacy_proposals

    root = output.parents[1]
    legacy_file = root / "data/processed/source_units.jsonl"
    old = (
        [
            json.loads(line)
            for line in legacy_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if legacy_file.is_file()
        else []
    )
    manifests = [
        read_json(p) for p in (root / "data/integration").glob("*.manifest.json")
    ]
    candidates = [{**p, "source_unit_id": p["probe_id"]} for p in probes]
    mapping = legacy_proposals(candidates, old, manifests)
    for row in mapping:
        row["source_probe_id"] = row.pop("new_source_unit_id")
        row["note"] = (
            "Locator proposal only; not a new SourceUnit or verified text equivalence"
        )
    write_json(output / "legacy-locator-crosswalk.json", mapping)
    write_json(
        output / "source-comparison-notes.json",
        config.get("source_comparison_notes", []),
    )
    write_json(
        output / "survey-report.json",
        {
            "document_sections": len(sections),
            "source_probes": len(probes),
            "probe_kinds": sorted({p["probe_kind"] for p in probes}),
            "expert_review": "unverified",
            "note": "Source probes are manually selected OCR spans, not MedicalStatements or LLM outputs.",
        },
    )
    return sections, probes
