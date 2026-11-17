"""Draft mode of the existing kg_v2 pipeline, with shared bounded transport."""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import httpx

from document_toolkit.checkpoint import CachedLLM, Checkpoint
from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import Settings
from document_toolkit.llm_client import LLMError
from knowledge_pipeline.pipeline import digest, jsonl

from .contracts import MEDICAL, RELATIONS, schemas
from .draft import resolve_draft, write_review_output
from .registry import load_registry
from .transport import BudgetedLLM, BudgetExhausted, RequestBudget

DRAFT_INSTRUCTION = """
Đầu ra dùng làm bản nháp có nguồn để người dùng review, không phải tri thức đã duyệt.
Ưu tiên giữ nội dung đầy đủ trong content của concept thích hợp, không chỉ tên:
định nghĩa, triệu chứng, chẩn đoán, chỉ định/chống chỉ định, điều kiện, ngoại lệ,
theo dõi sau xử trí. Không buộc mỗi ý thành một node/cạnh. Cite đủ mọi block quan trọng.
Context giúp xác định đối tượng; không cần tạo lại mọi subtype nếu không giúp giữ mục chính.
MANAGED_BY đi từ Condition đến Intervention, không đảo ngược. EVALUATED_BY đi từ
Condition đến DiagnosticMethod. Nếu taxonomy không diễn đạt chắc thì giữ content.
Vận dụng nguyên tắc là Skill nhận thức có căn cứ mục tiêu, không phải tự chứng minh thao tác.
Trích tất cả câu hỏi thật trong các block question, giữ câu con/options, answer null nếu sách
không có đáp án. Không tạo Skill từ việc đề bài chỉ nhắc tên một thao tác.
"""


def messages_for(window, prompt):
    keys = (
        "block_id",
        "text",
        "role",
        "section_title",
        "kind",
        "order",
        "parent_heading_ids",
        "system_heading_id",
        "parent_category_id",
        "category_code",
        "table_html",
    )
    payload = {
        "window_id": window["window_id"],
        "blocks": [{k: b[k] for k in keys if k in b} for b in window["blocks"]],
        "structural_links": window.get("structure", []),
    }
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def save_draft(
    candidates,
    audit,
    windows,
    catalog,
    output,
    registry_path,
    draft_registry_path,
    report,
):
    graph, identity = resolve_draft(
        candidates, load_registry(Path(registry_path)), draft_registry_path
    )
    audit.update(identity)
    audit["candidate-graph"] = candidates
    for name, rows in (("nodes", graph["nodes"]), ("edges", graph["edges"])):
        jsonl(Path(output) / (name + ".jsonl"), rows)
    write_json(Path(output) / "graph.json", graph)
    report.update(
        node_counts=dict(Counter(n["type"] for n in graph["nodes"])),
        edge_counts=dict(Counter(e["type"] for e in graph["edges"])),
    )
    report = write_review_output(output, graph, audit, windows, catalog, report)
    for name, value in audit.items():
        write_json(Path(output) / "audit" / (name + ".json"), value)
    write_json(Path(output) / "audit/report.json", report)
    return report


def run_draft(
    scope_path,
    output,
    *,
    settings=None,
    client=None,
    resume=False,
    dry_run=False,
    root=None,
    max_calls=6,
    timeout_seconds=60,
    total_seconds=360,
    registry_path=None,
    draft_registry_path=None,
    budget=None,
    attempts_per_window=2,
    no_response_timeout=False,
    connect_timeout_seconds=30,
):
    from .pipeline import HERE, ROOT, VERSION, compile_graph, prepare

    root = Path(root or ROOT)
    output = Path(output).resolve()
    if not output.is_relative_to((root / "data/knowledge-extraction/v2").resolve()):
        raise ValueError("draft_output_must_be_in_v2")
    if (
        not 1 <= max_calls <= 6
        or (not no_response_timeout and not 0 < total_seconds <= 360)
        or not 0 < timeout_seconds <= 60
        or not 1 <= attempts_per_window <= 2
        or connect_timeout_seconds <= 0
    ):
        raise ValueError("invalid_draft_limits")
    if no_response_timeout:
        total_seconds = None
    if (output / "audit/checkpoint-v2.json").exists() and (not resume or dry_run):
        raise ValueError("existing_draft_requires_resume")
    scope = read_json(Path(scope_path))
    prepared = prepare(scope, root)
    output.mkdir(parents=True, exist_ok=True)
    raw_schema, graph_schema = schemas()

    def write_prepared():
        for name, value in [
            ("catalog", prepared["catalog"]),
            ("sections", prepared["sections"]),
            ("ocr-manifest", prepared["ocr_metadata"]),
            ("windows", prepared["windows"]),
            ("extraction.schema", raw_schema),
            ("graph.schema", graph_schema),
        ]:
            write_json(output / "audit" / (name + ".json"), value)
        jsonl(output / "audit/pages.jsonl", prepared["pages"])

    if dry_run:
        write_prepared()
        report = {
            "status": "prepared",
            "windows": len(prepared["windows"]),
            "llm_calls": 0,
            "new_ocr_calls": 0,
            "preparation_rejected": prepared["preparation_rejected"],
        }
        write_json(output / "audit/report.json", report)
        return report
    settings = replace(
        settings or Settings.from_env(),
        llm_max_attempts=1,
        llm_timeout_seconds=timeout_seconds,
    )
    if not settings.llm_api_key or settings.llm_api_key.startswith("<"):
        raise ValueError("fill_llm_api_key_in_root_env")
    endpoint = settings.endpoint_url(settings.llm_chat_completions_endpoint)
    from urllib.parse import urlsplit

    url = urlsplit(endpoint)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("unsafe_endpoint_configuration")
    settings = replace(
        settings, max_output_tokens=min(settings.max_output_tokens, 8192)
    )
    prompt = (HERE / "extract-v2.txt").read_text(encoding="utf-8") + DRAFT_INSTRUCTION
    prompt += "\nCONTROLLED NODE TYPES: " + ", ".join(
        MEDICAL + ["Skill", "SampleQuestion"]
    )
    prompt += "\nCONTROLLED EDGE ENDPOINT TYPES:\n" + "\n".join(
        name + ": " + "|".join(sorted(domain)) + " -> " + "|".join(sorted(range_))
        for name, (domain, range_) in RELATIONS.items()
    )
    code = {p.name: digest(p) for p in HERE.glob("*.py")}
    generation = {
        "model": settings.model,
        "endpoint": endpoint,
        "timeout": timeout_seconds,
        "max_tokens": settings.max_output_tokens,
        "temperature": 0,
        "prompt_budget_bytes": settings.prompt_budget_bytes,
    }
    if no_response_timeout:
        generation.update(
            timeout=None,
            connect_timeout_seconds=connect_timeout_seconds,
            timeout_policy="connection_only",
        )
    # Operational allowance can change on resume; generation inputs cannot.
    signature = fingerprint(
        [
            VERSION,
            "draft-v1",
            prepared,
            prompt,
            raw_schema,
            graph_schema,
            generation,
            code,
        ]
    )
    checkpoint = Checkpoint(
        output / "audit/checkpoint-v2.json", signature, resume=resume
    )
    write_prepared()
    write_json(
        output / "audit/manifest.json",
        {
            "mode": "source_grounded_draft",
            "fingerprint": signature,
            "code": code,
            "generation": generation,
            "source_scope": scope,
            "publication_authorized": False,
            "neo4j_imported": False,
        },
    )
    (output / "audit/extract-v2.txt").write_text(prompt, encoding="utf-8")
    budget = budget or RequestBudget(max_calls, total_seconds)
    initial_calls = budget.calls
    metric_path = output / "audit/request-metrics.json"
    previous_metrics = read_json(metric_path) if metric_path.exists() else []
    recovery_path = output / "audit/partial-schema-recovery.json"
    recovery = read_json(recovery_path) if recovery_path.exists() else {}
    raw_windows, failures, hits = {}, [], 0
    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        transport=httpx.HTTPTransport(retries=0),
    ) as http:
        llm = client or BudgetedLLM(
            settings,
            http,
            budget,
            lambda rows: write_json(metric_path, previous_metrics + rows),
            no_response_timeout=no_response_timeout,
            connect_timeout_seconds=connect_timeout_seconds,
        )
        cached = CachedLLM(llm, checkpoint, namespace=endpoint)
        for w in prepared["windows"]:
            llm.window_id = w["window_id"]
            messages = messages_for(w, prompt)
            key = fingerprint([endpoint, settings.model, messages, raw_schema])
            was_cached = key in checkpoint.data["calls"]
            for attempt in range(attempts_per_window):
                if not was_cached and budget.calls - initial_calls >= max_calls:
                    failures.append(
                        {
                            "window_id": w["window_id"],
                            "category": "budget",
                            "reason": "invocation_request_budget_exhausted",
                        }
                    )
                    break
                try:
                    raw_windows[w["window_id"]] = cached.chat_json(
                        settings.model, messages, raw_schema
                    )
                    hits += int(was_cached)
                    write_json(
                        output / "audit/raw" / (w["window_id"] + ".json"),
                        raw_windows[w["window_id"]],
                    )
                    break
                except BudgetExhausted:
                    failures.append(
                        {
                            "window_id": w["window_id"],
                            "category": "budget",
                            "reason": "shared_budget_exhausted",
                        }
                    )
                    break
                except LLMError as exc:
                    diagnostics = exc.diagnostics
                    error_path = (
                        output
                        / "audit/raw"
                        / (w["window_id"] + f".attempt-{attempt + 1}.error.json")
                    )
                    event = 1
                    while error_path.exists():
                        event += 1
                        error_path = (
                            output
                            / "audit/raw"
                            / (
                                w["window_id"]
                                + f".attempt-{attempt + 1}.event-{event}.error.json"
                            )
                        )
                    write_json(error_path, diagnostics)
                    if diagnostics.get("category") == "schema":
                        from .recovery import recover_diagnostics

                        try:
                            original, projected, held = recover_diagnostics(
                                diagnostics, raw_schema
                            )
                        except (ValueError, KeyError):
                            pass
                        else:
                            wid = w["window_id"]
                            recovery[wid] = {
                                "rejected": held,
                                "original_response_file": "audit/raw/"
                                + wid
                                + ".original-response.json",
                            }
                            write_json(
                                output
                                / "audit/raw"
                                / (wid + ".original-response.json"),
                                original,
                            )
                            write_json(
                                output / "audit/raw" / (wid + ".json"), projected
                            )
                            write_json(recovery_path, recovery)
                            raw_windows[wid] = projected
                            checkpoint.data["calls"][key] = projected
                            checkpoint.save()
                            break
                    if (
                        diagnostics.get("retryable")
                        and attempt + 1 < attempts_per_window
                    ):
                        continue
                    failures.append(
                        {
                            "window_id": w["window_id"],
                            "category": diagnostics.get("category", "llm"),
                            "error_type": diagnostics.get(
                                "error_type", type(exc).__name__
                            ),
                            "http_status": diagnostics.get("http_status"),
                            "latency_seconds": diagnostics.get("latency_seconds"),
                        }
                    )
                    break
    candidates, audit = compile_graph(raw_windows, prepared["windows"], draft=True)
    if recovery:
        from .recovery import attach_recovery

        attach_recovery(audit, recovery)
    for f in failures:
        audit["review_items"].append({**f, "reason": "window_failed_reextract_queue"})
    capacity = [
        {
            "window_id": wid,
            "reason": "capacity_requires_review",
            "nodes": len(raw["nodes"]),
            "edges": len(raw["edges"]),
        }
        for wid, raw in raw_windows.items()
        if len(raw["nodes"]) >= 12 or len(raw["edges"]) >= 16
    ]
    audit["review_items"].extend(capacity)
    report = {
        "status": "partial_draft"
        if failures
        else "draft_with_records_held"
        if recovery
        else "draft_ready_for_review",
        "mode": "draft_extraction",
        "llm_calls_this_run": budget.calls - initial_calls,
        "cache_hits_this_run": hits,
        "shared_budget": budget.snapshot(),
        "windows_total": len(prepared["windows"]),
        "windows_with_raw_output": len(raw_windows),
        "failed_windows": failures,
        "partial_schema_windows": sorted(recovery),
        "capacity_review_windows": capacity,
        "new_ocr_calls": 0,
    }
    registry_path = registry_path or root / scope.get(
        "canonical_registry", "knowledge_pipeline/kg_v2/canonical-registry.json"
    )
    draft_registry_path = (
        draft_registry_path or root / "knowledge_pipeline/kg_v2/draft-registry.json"
    )
    report = save_draft(
        candidates,
        audit,
        prepared["windows"],
        prepared["catalog"],
        output,
        registry_path,
        draft_registry_path,
        report,
    )
    checkpoint.data["complete"] = not failures
    checkpoint.save()
    invocations = (
        read_json(output / "audit/invocations.json")
        if (output / "audit/invocations.json").exists()
        else []
    )
    write_json(output / "audit/invocations.json", invocations + [report])
    return report
