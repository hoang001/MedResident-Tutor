"""Sequential chapter shards with one total request budget and draft aggregation."""

from pathlib import Path

from jsonschema import Draft202012Validator

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.pipeline import jsonl

from .contracts import schemas
from .draft_run import save_draft
from .transport import RequestBudget


def combine_runs(sources, output, *, registry_path=None, draft_registry_path=None):
    from .pipeline import HERE, ROOT, compile_graph

    output = Path(output).resolve()
    if (
        not output.is_relative_to((ROOT / "data/knowledge-extraction/v2").resolve())
        or output.exists()
    ):
        raise ValueError("aggregate_requires_new_v2_output")
    windows, raw, pages, catalog, parents = {}, {}, {}, {}, []
    recovery, originals = {}, {}
    raw_schema, graph_schema = schemas()
    for source in sources:
        source = Path(source).resolve()
        if not source.is_relative_to((ROOT / "data/knowledge-extraction/v2").resolve()):
            raise ValueError("aggregate_parent_must_be_v2")
        if read_json(source / "audit/extraction.schema.json") != raw_schema:
            raise ValueError("aggregate_raw_schema_incompatible")
        parents.append(
            {
                "path": source.relative_to(ROOT).as_posix(),
                "manifest": read_json(source / "audit/manifest.json"),
            }
        )
        recovery_file = source / "audit/partial-schema-recovery.json"
        if recovery_file.exists():
            recovery.update(read_json(recovery_file))
        for window in read_json(source / "audit/windows.json"):
            wid = window["window_id"]
            if wid in windows and windows[wid] != window:
                raise ValueError("conflicting_window_inputs_no_silent_override")
            windows[wid] = window
            path = source / "audit/raw" / (wid + ".json")
            if path.exists():
                value = read_json(path)
                Draft202012Validator(raw_schema).validate(value)
                if wid in raw and value != raw[wid]:
                    raise ValueError("conflicting_raw_no_silent_override")
                raw[wid] = value
                original_file = source / "audit/raw" / (wid + ".original-response.json")
                if original_file.exists():
                    originals[wid] = read_json(original_file)
        import json

        for line in (
            (source / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines()
        ):
            page = json.loads(line)
            key = (page["source_id"], page["pdf_page"])
            if key in pages and pages[key] != page:
                raise ValueError("conflicting_corrected_page_revision")
            pages[key] = page
        for book in read_json(source / "audit/catalog.json"):
            catalog[book["source_id"]] = book
    candidates, audit = compile_graph(raw, list(windows.values()), draft=True)
    if recovery:
        from .recovery import attach_recovery

        attach_recovery(audit, recovery)
    for wid in windows.keys() - raw.keys():
        audit["review_items"].append(
            {"window_id": wid, "reason": "no_successful_raw_reextract_queue"}
        )
    output.mkdir(parents=True)
    for wid, value in raw.items():
        write_json(output / "audit/raw" / (wid + ".json"), value)
    for wid, value in originals.items():
        write_json(output / "audit/raw" / (wid + ".original-response.json"), value)
    for name, value in [
        ("windows", list(windows.values())),
        ("catalog", list(catalog.values())),
        ("extraction.schema", raw_schema),
        ("graph.schema", graph_schema),
    ]:
        write_json(output / "audit" / (name + ".json"), value)
    jsonl(output / "audit/pages.jsonl", list(pages.values()))
    write_json(
        output / "audit/manifest.json",
        {
            "mode": "explicit_draft_aggregation",
            "parents": parents,
            "distinct_generation_runs_preserved": True,
            "publication_authorized": False,
            "neo4j_imported": False,
        },
    )
    report = {
        "status": "draft_with_records_held" if recovery else "draft_ready_for_review",
        "mode": "draft_aggregation",
        "llm_calls_this_run": 0,
        "windows_total": len(windows),
        "windows_with_raw_output": len(raw),
        "partial_schema_windows": sorted(recovery),
    }
    return save_draft(
        candidates,
        audit,
        list(windows.values()),
        list(catalog.values()),
        output,
        registry_path or HERE / "canonical-registry.json",
        draft_registry_path or HERE / "draft-registry.json",
        report,
    )


def run_batch(
    plan_path,
    output,
    *,
    max_calls,
    total_seconds,
    timeout_seconds=60,
    resume=False,
    draft_registry_path=None,
    attempts_per_window=2,
    no_response_timeout=False,
    connect_timeout_seconds=30,
):
    from .pipeline import ROOT, run

    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / "data/knowledge-extraction/v2").resolve()):
        raise ValueError("batch_output_must_be_v2")
    if (
        not 0 < timeout_seconds <= 60
        or not 1 <= attempts_per_window <= 2
        or connect_timeout_seconds <= 0
    ):
        raise ValueError("invalid_batch_transport_limits")
    if no_response_timeout:
        total_seconds = None
    plan = read_json(Path(plan_path))
    for shard in plan["shards"]:
        key = shard["key"]
        if not key or Path(key).name != key or key in {".", ".."}:
            raise ValueError("invalid_shard_key")
        scope = (ROOT / shard["scope"]).resolve()
        if not scope.is_relative_to(ROOT):
            raise ValueError("scope_must_be_in_repo")
    plan_hash = fingerprint(
        [plan, [read_json(ROOT / s["scope"]) for s in plan["shards"]]]
    )
    state_path = output / "batch-state.json"
    if state_path.exists():
        if not resume:
            raise ValueError("batch_exists_use_resume")
        state = read_json(state_path)
        if state["plan_fingerprint"] != plan_hash:
            raise ValueError("batch_plan_changed_use_new_output")
    else:
        state = {"plan_fingerprint": plan_hash, "shards": {}, "invocations": []}
    output.mkdir(parents=True, exist_ok=True)
    budget = RequestBudget(max_calls, total_seconds)
    for shard in plan["shards"]:
        if (
            budget.calls >= max_calls
            or (total_seconds is not None and budget.wait_seconds >= total_seconds)
            or budget.blocked
        ):
            break
        folder = output / "shards" / shard["key"]
        shard_resume = (folder / "audit/checkpoint-v2.json").exists()
        result = run(
            ROOT / shard["scope"],
            folder,
            root=ROOT,
            draft=True,
            resume=shard_resume,
            max_calls=6,
            total_seconds=min(total_seconds, 360)
            if total_seconds is not None
            else None,
            timeout_seconds=timeout_seconds,
            draft_registry_path=draft_registry_path,
            budget=budget,
            attempts_per_window=attempts_per_window,
            no_response_timeout=no_response_timeout,
            connect_timeout_seconds=connect_timeout_seconds,
        )
        state["shards"][shard["key"]] = result
        state["current_budget"] = budget.snapshot()
        write_json(state_path, state)
        print(
            f"Shard {shard['key']}: {result['windows_with_raw_output']}/{result['windows_total']} windows; attempts {budget.calls}/{max_calls}",
            flush=True,
        )
    sources = [ROOT / p for p in plan.get("base_runs", [])]
    sources.extend(
        output / "shards" / s["key"]
        for s in plan["shards"]
        if (output / "shards" / s["key"] / "audit/manifest.json").exists()
    )
    state["invocations"].append(budget.snapshot())
    if sources:
        aggregate = output / ("aggregate-" + str(len(state["invocations"])).zfill(4))
        result = combine_runs(
            sources, aggregate, draft_registry_path=draft_registry_path
        )
        state["latest_aggregate"] = aggregate.relative_to(ROOT).as_posix()
        state["latest_result"] = result
        (output / "report.md").write_text(
            f"# Chapter draft progress\n\nLatest review: [{aggregate.name}/review.html]({aggregate.name}/review.html).\n\n{len(state['shards'])}/{len(plan['shards'])} shards started; {budget.calls} attempts in this invocation.\n",
            encoding="utf-8",
        )
    write_json(state_path, state)
    return {
        "mode": "sequential_draft_batch",
        "budget": budget.snapshot(),
        "shards_started": len(state["shards"]),
        "shards_total": len(plan["shards"]),
        "latest_aggregate": state.get("latest_aggregate"),
        "neo4j_imported": False,
    }
