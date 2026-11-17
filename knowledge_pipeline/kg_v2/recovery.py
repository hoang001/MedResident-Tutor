"""Keep independently valid records from a real, schema-rejected LLM response."""

from collections import Counter
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from document_toolkit.common import read_json, write_json
from document_toolkit.llm_client import parse_json_response


def project_records(value, schema):
    """Filter unusable records; never repair fields, invent content or reverse edges."""
    if not isinstance(value, dict) or set(value) != {"nodes", "edges"}:
        raise ValueError("unusable_response_envelope")
    if not all(isinstance(value[k], list) for k in ("nodes", "edges")):
        raise ValueError("unusable_response_lists")
    projected, rejected = {"nodes": [], "edges": []}, []
    for collection, kind in (("nodes", "node"), ("edges", "edge")):
        validator = Draft202012Validator(schema["properties"][collection]["items"])
        counts = Counter(
            r.get("local_id")
            for r in value[collection]
            if isinstance(r, dict) and isinstance(r.get("local_id"), str)
        )
        for row in value[collection]:
            errors = list(validator.iter_errors(row))
            identifier = row.get("local_id") if isinstance(row, dict) else None
            duplicate = identifier is not None and counts[identifier] > 1
            if errors or duplicate:
                rejected.append(
                    {
                        "kind": kind,
                        "local_id": identifier,
                        "reason": "duplicate_local_id_in_raw"
                        if duplicate
                        else "invalid_record_schema",
                        "schema_rules": sorted({e.validator for e in errors}),
                        "candidate": deepcopy(row),
                    }
                )
            else:
                projected[collection].append(deepcopy(row))
    Draft202012Validator(schema).validate(projected)
    return projected, rejected


def recover_diagnostics(diagnostics, schema):
    if diagnostics.get("category") != "schema":
        raise ValueError("only_schema_rejections_can_be_projected")
    attempts = diagnostics.get("attempts", [])
    if not attempts or attempts[-1].get("finish_reason") == "length":
        raise ValueError("complete_original_json_required")
    original = parse_json_response(attempts[-1]["raw_response"])
    projected, rejected = project_records(original, schema)
    return original, projected, rejected


def attach_recovery(audit, recovery):
    audit["partial-schema-recovery"] = recovery
    for wid, entry in recovery.items():
        audit["review_items"].append(
            {
                "window_id": wid,
                "reason": "partial_schema_response_valid_records_kept",
                "invalid_records": len(entry["rejected"]),
            }
        )
        for rejected in entry["rejected"]:
            item = {**rejected, "window_id": wid}
            audit["rejected"].append(item)
            audit["review_items"].append(
                {
                    **item,
                    "decision": "invalid_record_outside_graph_valid_peers_retained",
                }
            )


def recover_batch(source, output, *, draft_registry_path=None):
    """Explicit offline recovery into new output; leaves all original runs intact."""
    from .batch import combine_runs
    from .pipeline import ROOT
    from .revalidate import revalidate

    source, output = Path(source).resolve(), Path(output).resolve()
    allowed = (ROOT / "data/knowledge-extraction/v2").resolve()
    if (
        not source.is_relative_to(allowed)
        or not output.is_relative_to(allowed)
        or output.exists()
    ):
        raise ValueError("recovery_requires_existing_v2_source_and_new_output")
    state = read_json(source / "batch-state.json")
    sources = []
    for key in state["shards"]:
        shard = source / "shards" / key
        target = output / "shards" / key
        revalidate(
            shard,
            target,
            draft=True,
            recover_errors=True,
            draft_registry_path=draft_registry_path,
        )
        sources.append(target)
    result = combine_runs(
        sources, output / "aggregate", draft_registry_path=draft_registry_path
    )
    report = {
        "mode": "offline_schema_record_recovery",
        "parent_batch": source.relative_to(ROOT).as_posix(),
        "llm_calls_this_run": 0,
        "result": result,
        "review_file": "aggregate/review.html",
        "neo4j_imported": False,
    }
    write_json(output / "recovery-report.json", report)
    (output / "report.md").write_text(
        "# Khôi phục bản nháp từ response thật\n\nKhông gọi thêm LLM. Mở [review.html](aggregate/review.html) để xem node/cạnh và bản ghi bị giữ ngoài.\n\nResponse gốc và checkpoint ở batch cha được giữ nguyên; chỉ các record qua schema được dùng trong projection, không điền content hoặc sửa type/hướng cạnh.\n",
        encoding="utf-8",
    )
    return report
