"""Versioned, bounded extraction + source audit + content-only KG compilation."""

import json
import re
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator

from document_toolkit.checkpoint import CachedLLM, Checkpoint
from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import Settings
from document_toolkit.llm_client import LLMClient, LLMError
from knowledge_pipeline.ocr import provided_ocr_json
from knowledge_pipeline.pipeline import digest, jsonl
from knowledge_pipeline.validation import normalized

from .context import expand_node_content, normalize_edge_context, structure_window
from .contracts import MEDICAL, RELATIONS, schemas
from .corrections import correct_page
from .registry import load_registry, resolve_graph
from .validation import check_edge, cycle_if_added, supported_node

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
VERSION = "medical-kg-v2"


def prepare(scope, root=ROOT, max_window_bytes=12000):
    books = scope["documents"]
    callback, ocr_metadata = provided_ocr_json(root, books, root / "data/graduate")
    artifacts = {a["document_edition_id"]: a for a in ocr_metadata["artifacts"]}
    windows, pages, rejected, catalog = [], {}, [], []
    patches = read_json(root / scope["ocr_patches"]) if scope.get("ocr_patches") else []
    issues = read_json(root / scope["ocr_issues"]) if scope.get("ocr_issues") else []
    for book in books:
        artifact = artifacts[book["document_edition_id"]]
        if artifact["source_pdf_sha256"] != book["expected_sha256"]:
            raise ValueError("scope_pdf_hash_mismatch")
        pdf = root / book["repo_relative_path"]
        ocr = read_json(root / artifact["path"])
        page_rows = {r["page_start"]: r for r in ocr["sections"]}
        catalog.append({k: v for k, v in book.items() if k != "windows"})
        selected = {s["pdf_page"] for w in book["windows"] for s in w["selectors"]}
        if len(selected) > 20:
            raise ValueError("trial_page_limit_exceeded")
        for window in book["windows"]:
            blocks = []
            for selector in window["selectors"]:
                page = selector["pdf_page"]
                raw_text = callback(pdf, page)
                correction = correct_page(
                    raw_text,
                    patches,
                    source_id=book["source_id"],
                    page=page,
                    ocr_sha256=artifact["sha256"],
                    pdf_sha256=artifact["source_pdf_sha256"],
                    root=root,
                )
                text = correction["corrected_text"]
                pages[(book["source_id"], page)] = {
                    "source_id": book["source_id"],
                    "document_edition_id": book["document_edition_id"],
                    "pdf_page": page,
                    "text": text,
                    "html": page_rows[page].get("html"),
                    "read_method": page_rows[page].get("read_method"),
                    "ocr_sha256": artifact["sha256"],
                    "raw_text": raw_text,
                    "correction": correction,
                }
                start = (
                    text.index(selector["start_anchor"])
                    if selector.get("start_anchor")
                    else 0
                )
                end = (
                    text.index(selector["end_anchor"], start)
                    if selector.get("end_anchor")
                    else len(text)
                )
                if end <= start or not text[start:end].strip():
                    raise ValueError("empty_or_reversed_source_selection")
                block_id = (
                    "BLOCK2_"
                    + fingerprint(
                        [book["source_id"], artifact["sha256"], page, start, end]
                    )[:24]
                )
                block = {
                    "block_id": block_id,
                    "source_id": book["source_id"],
                    "document_edition_id": book["document_edition_id"],
                    "source_sha256": artifact["source_pdf_sha256"],
                    "ocr_sha256": artifact["sha256"],
                    "pdf_page": page,
                    "printed_page_label": book.get("verified_printed_labels", {}).get(
                        str(page)
                    ),
                    "section_id": window["section_id"],
                    "section_title": window["title"],
                    "role": selector["role"],
                    "char_start": start,
                    "char_end": end,
                    "text": text[start:end],
                    "correction": correction,
                    "continuation_verified": selector.get(
                        "continuation_verified", False
                    ),
                    "unresolved_issues": [
                        issue
                        for issue in issues
                        if issue["source_id"] == book["source_id"]
                        and issue["pdf_page"] == page
                        and issue.get("decision") == "unresolved"
                    ],
                }
                if selector["role"] == "table":
                    # A table is atomic: retain original layout rather than pretending flattened rows suffice.
                    html = page_rows[page].get("html", "")
                    tables = re.findall(
                        r"<table\b.*?</table>", html, re.DOTALL | re.IGNORECASE
                    )
                    if not tables:
                        rejected.append(
                            {"window": window["key"], "reason": "table_layout_missing"}
                        )
                        continue
                    block["table_html"] = "\n".join(tables)
                blocks.append(block)
            # Keep section, multi-page lists, tables and compound questions together.
            # Oversize atomic windows are deferred, never silently cut into partial assertions.
            if (
                not blocks
                or len(
                    json.dumps(
                        [
                            {
                                k: v
                                for k, v in b.items()
                                if k in ("text", "table_html", "role")
                            }
                            for b in blocks
                        ],
                        ensure_ascii=False,
                    ).encode()
                )
                > max_window_bytes
            ):
                rejected.append(
                    {
                        "window": window["key"],
                        "reason": "atomic_window_too_large_or_empty",
                    }
                )
                continue
            windows.append(
                structure_window(
                    {
                        "window_id": "WINDOW2_" + fingerprint(blocks)[:24],
                        "key": window["key"],
                        "blocks": blocks,
                    }
                )
                if scope.get("structured_context")
                else {
                    "window_id": "WINDOW2_" + fingerprint(blocks)[:24],
                    "key": window["key"],
                    "blocks": blocks,
                }
            )
    if len(windows) > 6:
        raise ValueError("trial_window_limit_exceeded")
    return {
        "windows": windows,
        "pages": list(pages.values()),
        "catalog": catalog,
        "sections": [
            {"source_id": b["source_id"], **s}
            for b in books
            for s in b.get("survey_sections", [])
        ],
        "ocr_metadata": ocr_metadata,
        "preparation_rejected": rejected,
    }


def compile_graph(raw_windows, windows, *, draft=False):
    from .draft import ReviewOnly, draft_edge, draft_node

    nodes, edge_candidates, rejected, locators, mappings = {}, [], [], {}, []
    structural_normalizations = []
    review_items = []
    for window in windows:
        raw = raw_windows.get(window["window_id"])
        if raw is None:
            continue
        blocks = {b["block_id"]: b for b in window["blocks"]}
        raw_names = {
            n["local_id"]: n.get("name", n.get("text", "")) for n in raw["nodes"]
        }
        local_nodes, seen = {}, set()
        for row in raw["nodes"]:
            if row["local_id"] in seen:
                raise ValueError("duplicate_local_node_id")
            seen.add(row["local_id"])
            try:
                grounded_row, events = expand_node_content(row, blocks)
                structural_normalizations.extend(events)
                if draft:
                    node, key, changes = draft_node(grounded_row, blocks, locators)
                    review_items.extend(
                        {
                            **c,
                            "candidate_id": node["id"],
                            "window_id": window["window_id"],
                            "local_id": row["local_id"],
                        }
                        for c in changes
                    )
                else:
                    node, key = supported_node(grounded_row, blocks, locators)
                local_nodes[row["local_id"]] = node
                if node["id"] in nodes:
                    existing = nodes[node["id"]]
                    if "content" in node:
                        for content in node["content"]:
                            if content not in existing["content"]:
                                existing["content"].append(content)
                        existing["content"].sort(key=fingerprint)
                else:
                    nodes[node["id"]] = node
                mappings.append(
                    {
                        "window_id": window["window_id"],
                        "local_id": row["local_id"],
                        "identity_key": key,
                        "candidate_id": node["id"],
                        "basis": "exact_source_anchored_identity",
                        "cross_source_auto_merge": False,
                    }
                )
            except ValueError as exc:
                target = (
                    review_items if draft and isinstance(exc, ReviewOnly) else rejected
                )
                target.append(
                    {
                        "kind": "node",
                        "window_id": window["window_id"],
                        "local_id": row["local_id"],
                        "reason": str(exc),
                        "candidate": row,
                    }
                )
        edge_ids = set()
        for row in raw["edges"]:
            if row["local_id"] in edge_ids:
                raise ValueError("duplicate_local_edge_id")
            edge_ids.add(row["local_id"])
            try:
                if draft:
                    edge, changes = draft_edge(row, local_nodes, blocks, locators)
                    review_items.extend(
                        {
                            **c,
                            "edge_id": edge["id"],
                            "window_id": window["window_id"],
                            "original": row,
                        }
                        for c in changes
                    )
                    edge_candidates.append(edge)
                else:
                    grounded_row, events = normalize_edge_context(
                        row, local_nodes, blocks
                    )
                    structural_normalizations.extend(events)
                    edge_candidates.append(
                        check_edge(grounded_row, local_nodes, blocks, locators)
                    )
            except ValueError as exc:
                target = (
                    review_items if draft and isinstance(exc, ReviewOnly) else rejected
                )
                target.append(
                    {
                        "kind": "edge",
                        "from_name": raw_names.get(row["from_id"], row["from_id"]),
                        "to_name": raw_names.get(row["to_id"], row["to_id"]),
                        "relation_type": row["type"],
                        "window_id": window["window_id"],
                        "local_id": row["local_id"],
                        "reason": str(exc),
                        "candidate": row,
                    }
                )
    edges = {}
    for edge in sorted(edge_candidates, key=lambda e: e["id"]):
        if cycle_if_added(edges.values(), edge):
            target = review_items if draft else rejected
            target.append(
                {"kind": "edge", "reason": "hierarchy_cycle", "candidate": edge}
            )
        else:
            edges[edge["id"]] = edge
    graph = {
        "schema_version": VERSION,
        "nodes": [nodes[k] for k in sorted(nodes)],
        "edges": [edges[k] for k in sorted(edges)],
    }
    Draft202012Validator(schemas()[1]).validate(graph)
    # Same-name / alias matching is a proposal only, never a canonical merge.
    proposals = []
    values = graph["nodes"]
    for i, left in enumerate(values):
        for right in values[i + 1 :]:
            if (
                left["type"] == right["type"]
                and left.get("name")
                and normalized(left["name"]).casefold()
                == normalized(right.get("name", "")).casefold()
            ):
                proposals.append(
                    {
                        "node_ids": [left["id"], right["id"]],
                        "method": "same_name_and_type",
                        "auto_merge": False,
                        "requires_identity_review": True,
                    }
                )
    return graph, {
        "rejected": rejected,
        "locators": list(locators.values()),
        "identity_registry": mappings,
        "merge_proposals": proposals,
        "structural_normalizations": structural_normalizations,
        "review_items": review_items,
    }


def run(
    scope_path,
    output,
    *,
    settings=None,
    client=None,
    resume=False,
    dry_run=False,
    root=ROOT,
    max_calls=6,
    timeout_seconds=60,
    total_seconds=360,
    registry_path=None,
    draft=False,
    draft_registry_path=None,
    budget=None,
    attempts_per_window=2,
    no_response_timeout=False,
    connect_timeout_seconds=30,
):
    if draft:
        from .draft_run import run_draft

        return run_draft(
            scope_path,
            output,
            settings=settings,
            client=client,
            resume=resume,
            dry_run=dry_run,
            root=root,
            max_calls=max_calls,
            timeout_seconds=timeout_seconds,
            total_seconds=total_seconds,
            registry_path=registry_path,
            draft_registry_path=draft_registry_path,
            budget=budget,
            attempts_per_window=attempts_per_window,
            no_response_timeout=no_response_timeout,
            connect_timeout_seconds=connect_timeout_seconds,
        )
    if no_response_timeout:
        raise ValueError("connection_only_timeout_requires_draft_or_batch")
    output = Path(output).resolve()
    if not output.is_relative_to((root / "data/knowledge-extraction/v2").resolve()):
        raise ValueError("v2_output_must_be_separate_from_v1")
    if (
        not 1 <= max_calls <= 6
        or not 1 <= timeout_seconds <= 60
        or not 1 <= total_seconds <= 360
    ):
        raise ValueError("invalid_trial_limits")
    if (output / "audit/checkpoint-v2.json").exists() and (not resume or dry_run):
        raise ValueError("existing_v2_run_requires_resume_or_new_output")
    prepared = prepare(read_json(scope_path), root)
    output.mkdir(parents=True, exist_ok=True)
    raw_schema, graph_schema = schemas()
    scope_config = read_json(scope_path)
    registry_path = (
        Path(registry_path)
        if registry_path
        else root
        / scope_config.get(
            "canonical_registry", "knowledge_pipeline/kg_v2/canonical-registry.json"
        )
    )

    def write_prepared():
        for name, value in (
            ("catalog", prepared["catalog"]),
            ("sections", prepared["sections"]),
            ("ocr-manifest", prepared["ocr_metadata"]),
            ("windows", prepared["windows"]),
            ("extraction.schema", raw_schema),
            ("graph.schema", graph_schema),
        ):
            write_json(output / "audit" / (name + ".json"), value)
        jsonl(output / "audit/pages.jsonl", prepared["pages"])

    if dry_run:
        write_prepared()
        report = {
            "status": "prepared",
            "windows": len(prepared["windows"]),
            "new_ocr_calls": 0,
            "llm_calls": 0,
            "preparation_rejected": prepared["preparation_rejected"],
        }
        write_json(output / "audit/report.json", report)
        return report
    settings = settings or Settings.from_env()
    settings = replace(
        settings,
        llm_max_attempts=1,
        llm_timeout_seconds=timeout_seconds,
        max_output_tokens=min(settings.max_output_tokens, 8192),
    )
    endpoint = settings.endpoint_url(settings.llm_chat_completions_endpoint)
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("unsafe_endpoint_configuration")
    prompt = (HERE / "extract-v2.txt").read_text(encoding="utf-8")
    prompt += "\nCONTROLLED NODE TYPES: " + ", ".join(
        MEDICAL + ["Skill", "SampleQuestion"]
    )
    prompt += "\nCONTROLLED EDGE ENDPOINT TYPES (mandatory):\n" + "\n".join(
        name + ": " + "|".join(sorted(domain)) + " -> " + "|".join(sorted(range_))
        for name, (domain, range_) in RELATIONS.items()
    )
    code = {p.name: digest(p) for p in HERE.glob("*.py")}
    toolkit = {p.name: digest(p) for p in (root / "document_toolkit").glob("*.py")}
    generation = {
        "model": settings.model,
        "endpoint": endpoint,
        "max_tokens": settings.max_output_tokens,
        "temperature": 0,
        "attempts": 1,
        "timeout": timeout_seconds,
        "prompt_budget_bytes": settings.prompt_budget_bytes,
        "max_calls": max_calls,
        "total_seconds": total_seconds,
    }
    signature = fingerprint(
        [VERSION, prepared, prompt, raw_schema, graph_schema, code, toolkit, generation]
    )
    checkpoint = Checkpoint(
        output / "audit/checkpoint-v2.json", signature, resume=resume
    )
    write_prepared()
    write_json(
        output / "audit/manifest.json",
        {
            "version": VERSION,
            "fingerprint": signature,
            "code": code,
            "toolkit": toolkit,
            "generation": generation,
            "source_scope": read_json(scope_path),
            "expert_review": "unverified",
            "publication_authorized": False,
            "neo4j_imported": False,
        },
    )
    (output / "audit/extract-v2.txt").write_text(prompt, encoding="utf-8")
    deadline = time.monotonic() + total_seconds
    calls, cache_hits, raw_windows, failures = 0, 0, {}, []
    metrics = []
    active_window = None
    request_started = None

    def record_request(request):
        nonlocal request_started
        request_started = time.monotonic()

    def record_response(response):
        response.read()
        row = {
            "window_id": active_window,
            "http_status": response.status_code,
            "latency_seconds": round(time.monotonic() - request_started, 3),
        }
        try:
            body = response.json()
            usage = body.get("usage", {})
            row["usage"] = (
                {k: v for k, v in usage.items() if isinstance(v, (int, float))}
                if isinstance(usage, dict)
                else {}
            )
            row["finish_reason"] = body.get("choices", [{}])[0].get("finish_reason")
        except (ValueError, AttributeError, IndexError, TypeError):
            row["usage"] = {}
        metrics.append(row)
        write_json(output / "audit/request-metrics.json", metrics)

    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        transport=httpx.HTTPTransport(retries=0),
        event_hooks={"request": [record_request], "response": [record_response]},
    ) as http:
        llm = client or LLMClient(settings, client=http)
        cached = CachedLLM(llm, checkpoint, namespace=endpoint)
        for window in prepared["windows"]:
            active_window = window["window_id"]
            payload = {
                "window_id": window["window_id"],
                "blocks": [
                    {k: b[k] for k in ("block_id", "text", "role", "section_title")}
                    | {
                        k: b[k]
                        for k in (
                            "kind",
                            "order",
                            "parent_heading_ids",
                            "system_heading_id",
                            "parent_category_id",
                            "category_code",
                        )
                        if k in b
                    }
                    | ({"table_html": b["table_html"]} if "table_html" in b else {})
                    for b in window["blocks"]
                ],
                "structural_links": window.get("structure", []),
            }
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            key = fingerprint([endpoint, settings.model, messages, raw_schema])
            uncached = key not in checkpoint.data["calls"]
            if uncached and (calls >= max_calls or time.monotonic() >= deadline):
                failures.append(
                    {
                        "window_id": window["window_id"],
                        "reason": "call_or_time_budget_exhausted",
                    }
                )
                continue
            if uncached:
                calls += 1
                if client is None:
                    llm._timeout = max(
                        0.1, min(timeout_seconds, deadline - time.monotonic())
                    )
            try:
                value = cached.chat_json(settings.model, messages, raw_schema)
                if not uncached:
                    cache_hits += 1
                raw_windows[window["window_id"]] = value
                write_json(
                    output / "audit/raw" / (window["window_id"] + ".json"), value
                )
            except Exception as exc:  # noqa: BLE001 -- isolate a failed window without logging secrets
                failure = {
                    "window_id": window["window_id"],
                    "reason": type(exc).__name__,
                }
                # Existing toolkit diagnostics are redacted; never serialize settings or headers.
                if isinstance(exc, LLMError) and exc.diagnostics:
                    write_json(
                        output / "audit/raw" / (window["window_id"] + ".error.json"),
                        exc.diagnostics,
                    )
                failures.append(failure)
    candidates, audit = compile_graph(raw_windows, prepared["windows"])
    graph, resolution = resolve_graph(candidates, load_registry(registry_path))
    audit.update(resolution)
    audit["candidate-graph"] = candidates
    for name in ("nodes", "edges"):
        jsonl(output / (name + ".jsonl"), graph[name])
    write_json(output / "graph.json", graph)
    for name, value in audit.items():
        write_json(output / "audit" / (name + ".json"), value)
    capacity_review = [
        {
            "window_id": wid,
            "nodes": len(raw["nodes"]),
            "edges": len(raw["edges"]),
            "reason": "prompt_capacity_reached_requires_coverage_review",
        }
        for wid, raw in raw_windows.items()
        if len(raw["nodes"]) >= 12 or len(raw["edges"]) >= 16
    ]
    report = {
        "status": "partial"
        if failures
        or audit["rejected"]
        or prepared["preparation_rejected"]
        or resolution["pending_identity_review"]
        or capacity_review
        else "complete_scope",
        "llm_calls_this_run": calls,
        "cache_hits_this_run": cache_hits,
        "request_metrics_this_run": metrics,
        "capacity_review_windows": capacity_review,
        "windows_with_raw_output": len(raw_windows),
        "windows_total": len(prepared["windows"]),
        "new_ocr_calls": 0,
        "node_counts": dict(Counter(n["type"] for n in graph["nodes"])),
        "edge_counts": dict(Counter(e["type"] for e in graph["edges"])),
        "rejected_records": len(audit["rejected"]),
        "unresolved_identities": len(resolution["pending_identity_review"]),
        "candidate_node_counts": dict(Counter(n["type"] for n in candidates["nodes"])),
        "candidate_edge_counts": dict(Counter(e["type"] for e in candidates["edges"])),
        "rejection_reasons": dict(Counter(r["reason"] for r in audit["rejected"])),
        "failed_windows": failures,
        "preparation_rejected": prepared["preparation_rejected"],
        "sample_questions": sum(n["type"] == "SampleQuestion" for n in graph["nodes"]),
        "question_scope_note": "Only explicit book questions in question-role blocks are eligible",
        "expert_review": "unverified",
        "semantic_support": "needs_manual_review",
        "publication_authorized": False,
        "neo4j_imported": False,
    }
    write_json(output / "audit/report.json", report)
    checkpoint.data["complete"] = not failures
    checkpoint.save()
    return report
