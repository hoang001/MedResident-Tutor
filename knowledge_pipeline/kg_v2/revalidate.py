"""Explicit offline revalidation; only reuse raw candidates with the exact same schema."""

import shutil
from collections import Counter
from pathlib import Path

from document_toolkit.common import read_json, write_json
from knowledge_pipeline.pipeline import digest, jsonl

from .contracts import schemas
from .loader import dry_run_loader
from .pipeline import HERE, ROOT, VERSION, compile_graph
from .registry import approve_decisions, load_registry, resolve_graph


def revalidate(
    source,
    output,
    *,
    registry_path=None,
    decisions_path=None,
    draft=False,
    draft_registry_path=None,
    recover_errors=False,
):
    source, output = Path(source).resolve(), Path(output).resolve()
    allowed = (ROOT / "data/knowledge-extraction/v2").resolve()
    if (
        not source.is_relative_to(allowed)
        or not output.is_relative_to(allowed)
        or output.exists()
    ):
        raise ValueError("offline_revalidation_requires_new_v2_output")
    raw_schema, graph_schema = schemas()
    if read_json(source / "audit/extraction.schema.json") != raw_schema:
        raise ValueError("raw_schema_changed_no_automatic_migration")
    windows = read_json(source / "audit/windows.json")
    raw_windows = {
        w["window_id"]: read_json(source / "audit/raw" / (w["window_id"] + ".json"))
        for w in windows
        if (source / "audit/raw" / (w["window_id"] + ".json")).exists()
    }
    recovery_file = source / "audit/partial-schema-recovery.json"
    recovery = read_json(recovery_file) if draft and recovery_file.exists() else {}
    originals = {}
    if recover_errors:
        if not draft:
            raise ValueError("partial_record_recovery_requires_draft")
        from .recovery import recover_diagnostics

        for window in windows:
            wid = window["window_id"]
            if wid in raw_windows:
                continue
            errors = sorted(
                (source / "audit/raw").glob(wid + ".*.error.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for path in errors:
                try:
                    original, projected, rejected = recover_diagnostics(
                        read_json(path), raw_schema
                    )
                except (ValueError, KeyError):
                    continue
                raw_windows[wid] = projected
                originals[wid] = original
                recovery[wid] = {
                    "original_error_file": path.relative_to(source).as_posix(),
                    "rejected": rejected,
                }
                break
    from jsonschema import Draft202012Validator

    for raw in raw_windows.values():
        Draft202012Validator(raw_schema).validate(raw)
    candidates, audit = compile_graph(raw_windows, windows, draft=draft)
    if recovery:
        from .recovery import attach_recovery

        attach_recovery(audit, recovery)
    registry_path = (
        Path(registry_path) if registry_path else HERE / "canonical-registry.json"
    )
    if draft and decisions_path:
        raise ValueError("draft_does_not_auto_approve_identity_decisions")
    registry = (
        approve_decisions(registry_path, candidates, read_json(decisions_path))
        if decisions_path
        else load_registry(registry_path)
    )
    graph, resolution = (
        (candidates, {"pending_identity_review": []})
        if draft
        else resolve_graph(candidates, registry)
    )
    audit.update(resolution)
    audit["candidate-graph"] = candidates
    for name in ("nodes", "edges"):
        jsonl(output / (name + ".jsonl"), graph[name])
    write_json(output / "graph.json", graph)
    for name in (
        "catalog.json",
        "sections.json",
        "ocr-manifest.json",
        "pages.jsonl",
        "windows.json",
        "extract-v2.txt",
    ):
        src = source / "audit" / name
        if src.exists():
            target = output / "audit" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
    shutil.copytree(source / "audit/raw", output / "audit/raw")
    for wid, original in originals.items():
        write_json(output / "audit/raw" / (wid + ".original-response.json"), original)
        write_json(output / "audit/raw" / (wid + ".json"), raw_windows[wid])
    if (source / "audit/checkpoint-v2.json").exists():
        shutil.copyfile(
            source / "audit/checkpoint-v2.json", output / "audit/parent-checkpoint.json"
        )
    write_json(output / "audit/extraction.schema.json", raw_schema)
    write_json(output / "audit/graph.schema.json", graph_schema)
    for name, value in audit.items():
        write_json(output / "audit" / (name + ".json"), value)
    write_json(
        output / "audit/manifest.json",
        {
            "version": VERSION,
            "mode": "explicit_offline_revalidation",
            "parent_run": source.relative_to(ROOT).as_posix(),
            "parent_manifest": read_json(source / "audit/manifest.json"),
            "validation_code": {p.name: digest(p) for p in HERE.glob("*.py")},
            "expert_review": "unverified",
            "publication_authorized": False,
            "neo4j_imported": False,
        },
    )
    report = {
        "status": "partial"
        if audit["rejected"] or resolution["pending_identity_review"]
        else "complete_scope",
        "mode": "offline_revalidation",
        "llm_calls_this_run": 0,
        "windows_total": len(windows),
        "windows_with_raw_output": len(raw_windows),
        "partial_schema_windows": sorted(recovery),
        "new_ocr_calls": 0,
        "node_counts": dict(Counter(n["type"] for n in graph["nodes"])),
        "edge_counts": dict(Counter(e["type"] for e in graph["edges"])),
        "rejected_records": len(audit["rejected"]),
        "unresolved_identities": len(resolution["pending_identity_review"]),
        "rejection_reasons": dict(Counter(r["reason"] for r in audit["rejected"])),
        "expert_review": "unverified",
        "semantic_support": "needs_manual_review",
        "sample_questions": sum(n["type"] == "SampleQuestion" for n in graph["nodes"]),
        "question_scope_note": "No explicit question blocks in this source scope",
        "publication_authorized": False,
        "neo4j_imported": False,
    }
    write_json(output / "audit/report.json", report)
    write_json(output / "audit/loader-preview.json", dry_run_loader(graph))
    if draft:
        from .draft_run import save_draft

        report = save_draft(
            candidates,
            audit,
            windows,
            read_json(output / "audit/catalog.json"),
            output,
            registry_path,
            draft_registry_path or HERE / "draft-registry.json",
            report,
        )
    return report
