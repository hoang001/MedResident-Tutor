"""Offline wrapper over document_toolkit, scoped, reproducible and review-gated."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.documents import chunk_sections, read_document
from document_toolkit.pipeline import extract_document

from .validation import normalized, validate_extraction

HERE = Path(__file__).parent
VERSION = "knowledge-extraction-v1"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(x, ensure_ascii=False, allow_nan=False) + "\n" for x in rows
        ),
        encoding="utf-8",
    )


def resolve_source(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Source must be an existing file inside repo")
    return path


def check_output(root, output):
    output = output.resolve()
    # Never write processed/pilot/training/curriculum inputs or source books.
    allowed = (root / "data/knowledge-extraction").resolve()
    if not output.is_relative_to(allowed):
        raise ValueError("Output must be inside data/knowledge-extraction")
    return output


def inventory(root, config, output):
    """Read all text layers, but never OCR the whole book."""
    from pypdf import PdfReader

    output = check_output(root, output)
    edition_ids = [b["document_edition_id"] for b in config["documents"]]
    if len(edition_ids) != len(set(edition_ids)):
        raise ValueError("Duplicate document edition ID")
    records = []
    for book in config["documents"]:
        path = resolve_source(root, book["repo_relative_path"])
        sha = digest(path)
        if book.get("expected_sha256") and sha != book["expected_sha256"]:
            raise ValueError("Document does not match scoped edition hash")
        reader = PdfReader(path)
        pages = []
        for number, page in enumerate(reader.pages, 1):
            try:
                raw = page.extract_text() or ""
                status = (
                    "text_layer_unreviewed" if raw.strip() else "unreadable_no_text"
                )
                error = None
            except Exception as exc:
                raw, status, error = "", "read_error", type(exc).__name__
            pages.append(
                {
                    "document_edition_id": book["document_edition_id"],
                    "source_id": book["source_id"],
                    "source_sha256": sha,
                    "pdf_page": number,
                    "printed_page_label": None,
                    "text": raw,
                    "read_method": "pdf_text",
                    "quality_status": status,
                    "error": error,
                }
            )
        jsonl(output / "pages" / f"{book['document_edition_id']}.jsonl", pages)
        count = sum(bool(x["text"].strip()) for x in pages)
        duplicates = [
            p.relative_to(root).as_posix()
            for p in (root / "data/raw-source").rglob("*.pdf")
            if p != path
            and p.stat().st_size == path.stat().st_size
            and digest(p) == sha
        ]
        records.append(
            {
                **book,
                "source_sha256": sha,
                "bytes": path.stat().st_size,
                "pdf_page_count": len(pages),
                "text_layer_pages": count,
                "pdf_text_status": "scan_no_text"
                if count == 0
                else "text_layer_with_empty_or_scan_pages"
                if count < len(pages)
                else "text_layer",
                "text_quality": "not_certified_by_text_layer_presence",
                "duplicate_files": duplicates,
                "unreadable_pages": [
                    x["pdf_page"] for x in pages if not x["text"].strip()
                ],
                "expert_review": "unverified",
                "course_id": None,
                "topic_id": None,
            }
        )
    record_schema = read_json(HERE / "schemas/records.schema.json")
    for record in records:
        Draft202012Validator(record_schema).validate(record)
    write_json(
        output / "inventory.json", {"schema_version": VERSION, "documents": records}
    )
    return records


def prepare(
    root, config, output, *, ocr_page=None, ocr_metadata=None, chunk_bytes=18000
):
    output = check_output(root, output)
    if chunk_bytes < 4:
        raise ValueError("chunk_bytes must be >=4")
    inventory_rows = read_json(output / "inventory.json")["documents"]
    records = {x["document_edition_id"]: x for x in inventory_rows}
    prepared = []
    report = {
        "mode": "dry_run",
        "llm_called": False,
        "documents": [],
        "expert_review": "unverified",
    }
    for book in config["documents"]:
        edition = book["document_edition_id"]
        inv = records[edition]
        path = resolve_source(root, book["repo_relative_path"])
        if digest(path) != inv["source_sha256"]:
            raise ValueError("PDF changed since inventory")
        selected = sorted(set(book["trial_pdf_pages"]))
        if len(selected) > 20:
            raise ValueError(
                "Trial capped at 20 pages per document; explicitly create another scope"
            )
        pages = sorted(set(selected + book["identity_pdf_pages"]))
        if len(pages) > 30:
            raise ValueError(
                "Selected OCR scope capped at 30 pages including identity pages"
            )
        if any(
            type(n) is not int or not 1 <= n <= inv["pdf_page_count"] for n in pages
        ):
            raise ValueError("Invalid page scope")
        # Toolkit's callback is local OCR only on explicitly selected pages.
        actual, page_errors = {}, {}
        for number in pages:
            try:
                document = read_document(
                    path,
                    page_numbers=[number],
                    ocr_page=ocr_page,
                    force_ocr=ocr_page is not None,
                )
                actual.update({x["page_start"]: x for x in document["sections"]})
            except Exception as exc:
                page_errors[number] = type(exc).__name__
        raw_pages = []
        spans = []
        for n in pages:
            row = actual.get(n)
            text = row["text"] if row else ""
            label = book.get("verified_printed_labels", {}).get(str(n))
            span = {
                "span_id": "SPAN_"
                + fingerprint([edition, inv["source_sha256"], n, text])[:24],
                "document_edition_id": edition,
                "source_id": book["source_id"],
                "source_sha256": inv["source_sha256"],
                "pdf_page": n,
                "printed_page_label": label,
                "text": text,
                "char_start": 0,
                "char_end": len(text),
                "read_method": row["read_method"] if row else "unreadable",
                "quality_status": "needs_review" if text.strip() else "unreadable",
                "ocr": ocr_metadata if row and row["read_method"] == "ocr" else None,
                "error": page_errors.get(n)
                or (None if text.strip() else "no_readable_text"),
            }
            raw_pages.append(span)
            if n in selected and text.strip():
                spans.append(span)
        jsonl(output / "raw" / f"{edition}.pages.jsonl", raw_pages)
        # Join only consecutive pages, preserving every original span and its boundary.
        groups = []
        for span in spans:
            if not groups or span["pdf_page"] != groups[-1][-1]["pdf_page"] + 1:
                groups.append([])
            groups[-1].append(span)
        sections = []
        for group in groups:
            # Budget-aware whole-page packing: never lose quote-to-page mapping.
            batch, size = [], 0
            for span in group:
                width = len(span["text"].encode("utf-8")) + 100
                if width > chunk_bytes:
                    # Toolkit can split text, but evidence spans remain the actual full page.
                    offset = 0
                    for part in chunk_sections(
                        [{"text": span["text"]}],
                        chunk_bytes - 100 if chunk_bytes > 104 else chunk_bytes,
                    ):
                        start = span["text"].index(part["text"], offset)
                        offset = start + len(part["text"])
                        if batch:
                            sections.append(make_section(batch))
                            batch, size = [], 0
                        sections.append(
                            make_section(
                                [
                                    {
                                        **span,
                                        "text": part["text"],
                                        "char_start": start,
                                        "char_end": offset,
                                        "span_id": span["span_id"]
                                        + "_"
                                        + part["chunk_id"],
                                    }
                                ]
                            )
                        )
                    continue
                if batch and size + width > chunk_bytes:
                    sections.append(make_section(batch))
                    batch, size = [], 0
                batch.append(span)
                size += width
            if batch:
                sections.append(make_section(batch))
        target = output / "raw" / f"{edition}.input.json"
        failed = [n for n in selected if n not in actual]
        write_json(target, {"sections": sections, "unreadable_pages": failed})
        # Reuse toolkit's actual structured-input reader/chunker. Metadata stays in each chunk.
        chunks = chunk_sections(read_document(target)["sections"], chunk_bytes + 1000)
        write_json(output / "raw" / f"{edition}.chunks.json", chunks)
        prepared.append((book, target, chunks))
        report["documents"].append(
            {
                "document_edition_id": edition,
                "selected_pages": selected,
                "unreadable_pages": failed,
                "chunks": len(chunks),
                "page_errors": page_errors,
                "quality_review_pages": [s["pdf_page"] for s in spans],
                "unprocessed_pages": [
                    n for n in range(1, inv["pdf_page_count"] + 1) if n not in pages
                ],
            }
        )
    report["status"] = (
        "partial_reading"
        if any(d["unreadable_pages"] or d["page_errors"] for d in report["documents"])
        else "complete_trial_reading_not_extracted"
    )
    report["extracted_record_counts"] = {
        "source_units": 0,
        "concept_candidates": 0,
        "medical_statements": 0,
    }
    write_json(output / "dry-run-report.json", report)
    return prepared, report


def make_section(spans):
    return {
        "page_start": spans[0]["pdf_page"],
        "page_end": spans[-1]["pdf_page"],
        "source_spans": spans,
        "document_edition_id": spans[0]["document_edition_id"],
        "source_id": spans[0]["source_id"],
        "original_pdf_sha256": spans[0]["source_sha256"],
        "text": "\n\n".join(
            f"[PDF_PAGE={s['pdf_page']};SPAN={s['span_id']}]\n{s['text']}"
            for s in spans
        ),
    }


def extract(
    prepared, output, *, settings, resume=False, force=False, chunk_bytes=18000
):
    if not settings.llm_base_url or not settings.model:
        raise ValueError(
            "Extraction requires explicitly configured LLM_BASE_URL and LLM_MODEL"
        )
    from urllib.parse import urlsplit

    parsed = urlsplit(settings.llm_base_url)
    if (
        parsed.scheme not in ("https", "http")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Endpoint must be HTTP(S), without credentials/query/fragment")
    schema = read_json(HERE / "schemas/extraction.schema.json")
    prompt = (HERE / "prompts/extract.txt").read_text(encoding="utf-8")
    # Wrapper code, all dependencies, OCR content and model settings affect checkpoint identity.
    code = {p.name: digest(p) for p in HERE.glob("*.py")}
    deps = {k: importlib.metadata.version(k) for k in ("pypdf", "jsonschema", "httpx")}
    schemas = {p.name: digest(p) for p in (HERE / "schemas").glob("*.json")}
    generation = {
        "temperature": 0,
        "max_output_tokens": settings.max_output_tokens,
        "prompt_budget_bytes": settings.prompt_budget_bytes,
        "max_attempts": settings.llm_max_attempts,
        "timeout_seconds": settings.llm_timeout_seconds,
    }
    signature = fingerprint(
        [VERSION, code, deps, schemas, schema, prompt, chunk_bytes, generation]
    )
    config_dir = output / "runs" / "config" / signature
    write_json(config_dir / "extraction.schema.json", schema)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "extract.txt").write_text(prompt, encoding="utf-8")
    write_json(
        config_dir / "manifest.json",
        {
            "version": VERSION,
            "fingerprint": signature,
            "model": settings.model,
            "model_revision": "unverified_not_supplied_by_endpoint",
            "endpoint": settings.endpoint_url(settings.llm_chat_completions_endpoint),
            "schema_sha256": schemas,
            "prompt_sha256": digest(HERE / "prompts/extract.txt"),
            "code_sha256": code,
            "dependencies": deps,
            "generation": generation,
            "chunk_bytes": chunk_bytes,
            "expert_review": "unverified",
        },
    )
    write_json(
        output / "runs" / "validation-report.json",
        {
            "status": "in_progress",
            "fingerprint": signature,
            "default_evidence_count": 0,
            "expert_review": "unverified",
        },
    )
    results = []
    for book, target, chunks in prepared:
        value = extract_document(
            target,
            output / "runs" / f"{book['document_edition_id']}.raw.json",
            settings=settings,
            prompt=prompt,
            schema=schema,
            resume=resume,
            force=force,
            max_chunk_bytes=chunk_bytes + 1000,
            validator=lambda v, c: validate_extraction(v, c, schema),
            validator_version=signature,
        )
        results.append((book, value, chunks))
    return export_candidates(results, output, settings.model, signature, schema)


def export_candidates(results, output, model, signature, schema):
    units, concepts, statements, failures = {}, {}, {}, []
    run_id = "RUN_" + fingerprint([signature, model, [r for _, r, _ in results]])[:24]
    for book, result, chunks in results:
        chunk_map = {c["chunk_id"]: c for c in chunks}
        failures.extend(result["failures"])
        for item in result["results"]:
            chunk = chunk_map[item["chunk_id"]]
            value = item["extraction"]
            validation = validate_extraction(value, chunk, schema)
            spans = {s["span_id"]: s for s in chunk["source_spans"]}
            provenance = {
                "document_edition_id": book["document_edition_id"],
                "source_id": book["source_id"],
                "source_sha256": chunk["original_pdf_sha256"],
                "extraction_run_id": run_id,
                "schema_prompt_code_fingerprint": signature,
                "model": model,
                "validation": validation,
                "expert_review": "unverified",
                "usable_as_default_evidence": False,
                "course_id": None,
                "topic_id": None,
                "chunk_ids": [chunk["chunk_id"]],
            }
            local_units, local_concepts = {}, {}
            for row in value["source_units"]:
                supports = [
                    {
                        **s,
                        "normalized_quote": normalized(s["quote"]),
                        **{
                            k: spans[s["span_id"]][k]
                            for k in (
                                "pdf_page",
                                "printed_page_label",
                                "quality_status",
                                "read_method",
                                "char_start",
                                "char_end",
                            )
                        },
                    }
                    for s in row["supports"]
                ]
                identifier = (
                    "XSU_"
                    + fingerprint(
                        [
                            book["document_edition_id"],
                            provenance["source_sha256"],
                            supports,
                        ]
                    )[:24]
                )
                local_units[row["local_id"]] = identifier
                units[identifier] = {
                    **provenance,
                    "source_unit_id": identifier,
                    "title": row["title"],
                    "supports": supports,
                }
            for row in value["concepts"]:
                identifier = (
                    "MCC_"
                    + fingerprint(
                        [
                            book["document_edition_id"],
                            row["verbatim_name"],
                            row["concept_type"],
                            sorted(local_units[x] for x in row["source_unit_ids"]),
                        ]
                    )[:24]
                )
                local_concepts[row["local_id"]] = identifier
                concepts[identifier] = {
                    **provenance,
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("local_id", "source_unit_ids")
                    },
                    "concept_candidate_id": identifier,
                    "canonical_concept_id": None,
                    "source_unit_ids": [local_units[x] for x in row["source_unit_ids"]],
                }
            for row in value["statements"]:
                mapped = {
                    **row,
                    "source_unit_ids": [local_units[x] for x in row["source_unit_ids"]],
                    "concept_ids": [local_concepts[x] for x in row["concept_ids"]],
                }
                if row["relation"]:
                    mapped["relation"] = {
                        **row["relation"],
                        "subject_concept_id": local_concepts[
                            row["relation"]["subject_concept_id"]
                        ],
                        "object_concept_id": local_concepts[
                            row["relation"]["object_concept_id"]
                        ],
                    }
                mapped.pop("local_id")
                identifier = (
                    "MST_"
                    + fingerprint(
                        [
                            book["document_edition_id"],
                            provenance["source_sha256"],
                            mapped,
                        ]
                    )[:24]
                )
                statements[identifier] = {
                    **provenance,
                    **mapped,
                    "statement_id": identifier,
                }
    for name, rows in (
        ("source_units", units),
        ("concept_candidates", concepts),
        ("medical_statements", statements),
    ):
        record_schema = read_json(HERE / "schemas/records.schema.json")
        for record in rows.values():
            Draft202012Validator(record_schema).validate(record)
        jsonl(
            output / "runs" / "validated" / (name + ".jsonl"),
            [rows[k] for k in sorted(rows)],
        )
    # Equality only proposes a reviewable cross-source match; no canonical concept or merged statement.
    matches = []
    values = list(concepts.values())
    for i, left in enumerate(values):
        for right in values[i + 1 :]:
            if (
                left["document_edition_id"] != right["document_edition_id"]
                and normalized(left["proposed_name"]).casefold()
                == normalized(right["proposed_name"]).casefold()
            ):
                matches.append(
                    {
                        "candidate_ids": [
                            left["concept_candidate_id"],
                            right["concept_candidate_id"],
                        ],
                        "method": "exact_proposed_name",
                        "status": "needs_review",
                        "auto_merge": False,
                        "statement_comparison": "not_assessed",
                        "potential_conflict": None,
                    }
                )
    write_json(output / "runs" / "validated" / "concept-match-proposals.json", matches)
    from .mapping import legacy_proposals

    root = output.parents[1]
    legacy = root / "data/processed/source_units.jsonl"
    old = (
        [
            json.loads(line)
            for line in legacy.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if legacy.is_file()
        else []
    )
    manifests = [
        read_json(p) for p in (root / "data/integration").glob("*.manifest.json")
    ]
    write_json(
        output / "runs" / "validated" / "legacy-mapping-proposals.json",
        legacy_proposals(list(units.values()), old, manifests),
    )
    report = {
        "extraction_run_id": run_id,
        "status": "complete_scope"
        if all(r["status"] == "complete" for _, r, _ in results)
        else "partial",
        "counts": {
            "source_units": len(units),
            "concept_candidates": len(concepts),
            "medical_statements": len(statements),
        },
        "failures": failures,
        "expert_review": "unverified",
        "default_evidence_count": 0,
        "semantic_support": "needs_review",
        "model": model,
        "fingerprint": signature,
    }
    write_json(output / "runs" / "validation-report.json", report)
    return report
