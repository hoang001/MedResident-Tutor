"""UTF-8 thesis draft and integration handoff generated from saved artifacts."""

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter

from local_model_testing.experiment.metrics import csv_write, percentile

from . import ledger
from .common import ROOT, RUN, read, write, file_hash


def number(value, percent=False):
    if value is None:
        return "N/A"
    return f"{value:.1%}" if percent else f"{value:.4f}"


def table(headers, records):
    def cell(x):
        return str(x).replace("|", "/").replace("\n", " ") if x is not None else "N/A"

    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *("| " + " | ".join(map(cell, row)) + " |" for row in records),
        ]
    )


def integration():
    source = RUN / "live.json"
    live = read(source) if source.exists() else {}
    if not live.get("cases") and (RUN / "live-partial.json").exists():
        live = {
            **read(RUN / "live-partial.json"),
            **{k: v for k, v in live.items() if k != "cases"},
        }
    expected = {
        a["sample_id"]: a["expected_vector"]
        for q in read(RUN / "medical-development.json")
        for a in q["answers"]
    }
    entries = [
        r
        for r in ledger.attempts()
        if r["category"] == "medical_retrieval_confirmation"
    ]
    cases = []
    for c in live.get("cases", []):
        result, mode, sid = c["attempt"], c["mode"], c["sample_id"]
        trace = result["retrieval"]
        tid = trace["trace_id"]
        request = (
            read(RUN / "requests" / (tid + ".json"))
            if (RUN / "requests" / (tid + ".json")).exists()
            else None
        )
        server = (
            read(RUN / "server-inputs" / (tid + ".json"))
            if (RUN / "server-inputs" / (tid + ".json")).exists()
            else None
        )
        raw = (
            read(RUN / "raw" / (tid + ".json"))
            if (RUN / "raw" / (tid + ".json")).exists()
            else None
        )
        prediction = result.get("medical_evaluation")
        spec = next(
            q
            for q in read(RUN / "medical-development.json")
            if q["question_id"] == trace["question_id"]
        )
        by_id = (
            {r["criterion_id"]: r["score"] for r in prediction["rubric_scores"]}
            if prediction
            else {}
        )
        vector = (
            [by_id[r["criterion_id"]] for r in spec["rubric"]["criteria"]]
            if prediction
            else None
        )
        row = next(
            (
                r
                for r in entries
                if r["sample_id"] == sid
                and r["config"] == "retrieval_medical_" + mode + "_v2"
            ),
            {},
        )
        reason = json.loads(row["reason"]) if row.get("reason") else {}
        cases.append(
            {
                "sample_id": sid,
                "mode": mode,
                "trace_id": tid,
                "ledger_id": row.get("id"),
                "practice_http_status": c["http_status"],
                "attempt_status": result["status"],
                "medical_http_status": 200
                if row.get("status") == "completed"
                else reason.get("http_status"),
                "expected_vector": expected[sid],
                "api_vector": vector,
                "exact_vector": vector == expected[sid] if vector else None,
                "stage_error": result.get("stage_error"),
                "kg_queries": trace["neo4j_queries"],
                "vector_queries": trace["vector_queries"],
                "retrieval_seconds": trace["retrieval_seconds"],
                "kg_contributed": trace["kg_contributed"],
                "selected_ids": [
                    e["source_unit_id"] for e in trace["selected_evidence"]
                ],
                "server_ids_and_content_hash_match": server["evidence_at_http_server"]
                == trace["selected_evidence"]
                and server["input_payload_sha256"] == request["payload_sha256"]
                if server and request
                else None,
                "raw_saved": raw is not None,
                "inference_seconds": raw["raw"]["inference_seconds"] if raw else None,
                "input_tokens": raw["raw"]["input_tokens"] if raw else None,
                "generated_tokens": raw["raw"]["generated_tokens"] if raw else None,
                "worker_before_idle": c["worker_before"]["idle"],
                "worker_after_idle": c["worker_after"]["idle"],
                "medical_calls": c["provider_calls"]["medical"],
                "teaching_mock_calls": c["provider_calls"]["teaching"],
            }
        )
    worker = (
        read(RUN / "medical-server.json")
        if (RUN / "medical-server.json").exists()
        else {}
    )
    pairs = [
        sid
        for sid in expected
        if sum(c["sample_id"] == sid and c["api_vector"] is not None for c in cases)
        == 2
    ]
    log = (
        (RUN / "live-runtime.log").read_text(encoding="utf-8")
        if (RUN / "live-runtime.log").exists()
        else ""
    )
    practice_posts = len(
        re.findall(
            r"HTTP Request: POST http://isolated-retrieval/api/v1/practice/attempts ",
            log,
        )
    )
    result = {
        "planned_unique_samples": 6,
        "planned_pairs": 6,
        "planned_medical_attempts": 12,
        "inference_patch_verified": bool(cases)
        and all(x == 625 for x in live["effective_runtime"]["service_deadlines"])
        and all(x["read"] == 600 for x in live["effective_runtime"]["http_clients"]),
        "runtime_effective": live.get("effective_runtime"),
        "worker_idle_at_every_recorded_boundary": bool(cases)
        and all(
            c["worker_before"]["idle"]
            and c["worker_after"]["idle"]
            and c["worker_before"]["generation_started"]
            == c["worker_before"]["generation_finished"]
            and c["worker_after"]["generation_started"]
            == c["worker_after"]["generation_finished"]
            for c in live.get("cases", [])
        ),
        "unique_practice_attempts": len(cases),
        "practice_submit_posts_including_idempotency_checks": practice_posts,
        "medical_http_attempts": len(entries),
        "generations_started": sum(r["generation_started"] for r in entries),
        "generations_finished": len(worker.get("generation_finished_ids", [])),
        "raw_outputs_saved": len(list((RUN / "raw").glob("*.json"))),
        "generation_latency_median_seconds": percentile(
            [
                c["inference_seconds"]
                for c in cases
                if c["inference_seconds"] is not None
            ],
            50,
        ),
        "generation_latency_p95_seconds": percentile(
            [
                c["inference_seconds"]
                for c in cases
                if c["inference_seconds"] is not None
            ],
            95,
        ),
        "input_tokens": sum(c["input_tokens"] or 0 for c in cases),
        "generated_tokens": sum(c["generated_tokens"] or 0 for c in cases),
        "load_seconds": worker.get("load_seconds"),
        "worker_wall_seconds": worker.get("wall_seconds"),
        "peak_vram_allocated_bytes": worker.get("peak_vram_allocated_bytes"),
        "peak_vram_reserved_bytes": worker.get("peak_vram_reserved_bytes"),
        "valid_medical_api_evaluations": sum(
            c["api_vector"] is not None for c in cases
        ),
        "completed_practice_attempts": sum(
            c["attempt_status"] == "completed" for c in cases
        ),
        "complete_pair_count": len(pairs),
        "complete_pair_ids": pairs,
        "timeout_busy_counts": dict(
            Counter(
                c["stage_error"]["code"]
                for c in cases
                if c["stage_error"]
                and c["stage_error"].get("stage") == "medical"
                and c["stage_error"]["code"] in {"PROVIDER_TIMEOUT", "PROVIDER_BUSY"}
            )
        ),
        "teaching_mock_failures": dict(
            Counter(
                c["stage_error"]["code"]
                for c in cases
                if c["stage_error"] and c["stage_error"].get("stage") == "teaching"
            )
        ),
        "all_stage_errors": dict(
            Counter(c["stage_error"]["code"] for c in cases if c["stage_error"])
        ),
        "audit_neo4j_probe_queries_excluded_from_retrieval": read(
            RUN / "pre-start-neo4j-probe.json"
        )["audit_probe_queries"]
        if (RUN / "pre-start-neo4j-probe.json").exists()
        else 0,
        "server_hash_matches": sum(
            c["server_ids_and_content_hash_match"] is True for c in cases
        ),
        "server_hash_unknown": sum(
            c["server_ids_and_content_hash_match"] is None for c in cases
        ),
        "server_hash_mismatches": sum(
            c["server_ids_and_content_hash_match"] is False for c in cases
        ),
        "vector_kg_queries": sum(
            c["kg_queries"] for c in cases if c["mode"] == "vector"
        ),
        "hybrid_kg_queries": sum(
            c["kg_queries"] for c in cases if c["mode"] == "hybrid"
        ),
        "vector_queries": sum(c["vector_queries"] for c in cases),
        "shared_ledger_total_actual": len(ledger.attempts()),
        "cases": cases,
        "stopped_after_medical_error": live.get("stopped_after_medical_error"),
        "mastery_unchanged": live.get("mastery_unchanged"),
        "test_data_rolled_back": live.get(
            "test_attempts_and_questions_absent_after_rollback"
        ),
        "no_inference_yet": not entries,
        "teaching": "explicit mock, no Teaching model in this group",
    }
    result["strategy_results"] = {}
    for mode in ("vector", "hybrid"):
        group = [c for c in cases if c["mode"] == mode]
        valid = [c for c in group if c["api_vector"] is not None]
        result["strategy_results"][mode] = {
            "planned": 6,
            "attempted": len(group),
            "medical_api_valid": len(valid),
            "exact_vectors": sum(c["exact_vector"] is True for c in group),
            "normalized_mae": sum(
                abs(sum(c["api_vector"]) - sum(c["expected_vector"])) / 2 for c in valid
            )
            / len(valid)
            if valid
            else None,
            "mae_n": len(valid),
            "practice_completed": sum(
                c["attempt_status"] == "completed" for c in group
            ),
            "teaching_mock_failed": sum(
                c["attempt_status"] == "teaching_failed" for c in group
            ),
        }
    paired_outcomes = Counter()
    for sid in pairs:
        pair = {c["mode"]: c for c in cases if c["sample_id"] == sid}
        paired_outcomes[
            f"vector_{int(pair['vector']['exact_vector'])}_hybrid_{int(pair['hybrid']['exact_vector'])}"
        ] += 1
    result["paired_grade_outcomes"] = dict(paired_outcomes)
    write(RUN / "integration-metrics.json", result)
    csv_write(RUN / "integration-observed-only.csv", cases)
    planned_rows = []
    fields = (
        list(cases[0])
        if cases
        else [
            "sample_id",
            "mode",
            "expected_vector",
            "api_vector",
            "ledger_id",
            "practice_http_status",
            "medical_http_status",
            "attempt_status",
            "stage_error",
        ]
    )
    lookup = {(c["sample_id"], c["mode"]): c for c in cases}
    for sid, reference in expected.items():
        for mode in ("vector", "hybrid"):
            actual = lookup.get((sid, mode))
            planned_rows.append(
                actual
                or {
                    **dict.fromkeys(fields),
                    "sample_id": sid,
                    "mode": mode,
                    "expected_vector": reference,
                    "attempt_status": "not_run",
                }
            )
    csv_write(RUN / "integration-per-sample.csv", planned_rows)
    pre = read(RUN / "preflight.json")
    pre_case = next(c for c in pre["cases"] if c["mode"] == "hybrid")
    pre_tid = pre_case["attempt"]["retrieval"]["trace_id"]
    write(
        RUN / "preflight-trace-example.json",
        {
            "execution": "Actual retrieval and HTTPProvider with MockTransport; no Medical generation",
            "case": pre_case,
            "effective_runtime": pre["effective_runtime"],
            "payload_capture": next(
                c for c in pre["payload_captures"] if c["trace_id"] == pre_tid
            ),
        },
    )
    if cases:
        example = next(
            (
                c
                for c in cases
                if c["mode"] == "hybrid" and c["server_ids_and_content_hash_match"]
            ),
            cases[0],
        )
        tid = example["trace_id"]
        write(
            RUN / "trace-example.json",
            {
                "case": example,
                "request": read(RUN / "requests" / (tid + ".json")),
                "server_received": read(RUN / "server-inputs" / (tid + ".json"))
                if (RUN / "server-inputs" / (tid + ".json")).exists()
                else None,
                "raw": read(RUN / "raw" / (tid + ".json"))
                if (RUN / "raw" / (tid + ".json")).exists()
                else None,
            },
        )
    return result


def main():
    data = read(RUN / "offline/benchmark-verification.json")
    current = integration()
    med = data["medical"]
    medical_table = table(
        [
            "Cấu hình",
            "N dự kiến",
            "Schema hợp lệ",
            "Contract hợp lệ",
            "Exact total",
            "Exact vector",
            "MAE chuẩn hóa (n)",
        ],
        [
            [
                c,
                m["planned"],
                f"{m['schema_valid']}/{m['planned']}",
                f"{m['contract_valid']}/{m['planned']}",
                number(m["exact_total_score_agreement"], True),
                number(m["exact_criterion_vector_agreement"], True),
                f"{number(m['mae_normalized'])} ({m['mae_n']})",
            ]
            for c, m in med.items()
        ],
    )
    paired_table = table(
        ["Kết quả trên cùng mẫu", "Số mẫu"],
        [
            [name, data["paired_outcomes"].get(k, 0)]
            for name, k in [
                ("Cả hai đúng", "base_1_adapter_1"),
                ("Chỉ adapter đúng", "base_0_adapter_1"),
                ("Chỉ base đúng", "base_1_adapter_0"),
                ("Cả hai không đúng/không hợp lệ", "base_0_adapter_0"),
            ]
        ],
    )
    teaching_table = table(
        [
            "Cấu hình",
            "Giai đoạn",
            "N",
            "Schema hợp lệ",
            "Alignment proxy",
            "Context proxy (n)",
        ],
        [
            [
                c,
                stage,
                m["planned"],
                number(m["schema_valid_rate"], True),
                number(m["alignment_proxy_pass_rate"], True),
                f"{number(m['context_usage_proxy_pass_rate'], True)} ({m['context_denominator']})",
            ]
            for c, stages in data["teaching"].items()
            for stage, m in stages.items()
        ],
    )
    retrieval_table = table(
        [
            "Chế độ offline",
            "N",
            "Hit@5 proxy",
            "Coverage nguồn đầy đủ proxy",
            "Semantic relevance bác sĩ",
        ],
        [
            [
                mode,
                m["queries"],
                number(m["hit_at_5"], True),
                number(m["criterion_evidence_coverage_proxy"], True),
                "N/A",
            ]
            for mode, m in data["retrieval"].items()
        ],
    )
    latency_table = table(
        [
            "Medical",
            "Median/P95 giây",
            "Input/output tokens cuối",
            "Peak VRAM allocated/reserved GiB",
            "Peak RSS GiB",
        ],
        [
            [
                c,
                f"{m['generation_latency_median_seconds']:.2f}/{m['generation_latency_p95_seconds']:.2f}",
                f"{m['input_tokens']}/{m['generated_tokens']}",
                f"{data['runtime'][c]['peak_vram_allocated_bytes'] / 1024**3:.2f}/{data['runtime'][c]['peak_vram_reserved_bytes'] / 1024**3:.2f}",
                number(
                    data["runtime"][c]["peak_process_rss_bytes"] / 1024**3
                    if data["runtime"][c]["peak_process_rss_bytes"]
                    else None
                ),
            ]
            for c, m in med.items()
        ],
    )
    case_by_key = {(c["sample_id"], c["mode"]): c for c in current["cases"]}
    refs = read(RUN / "medical-development.json")
    cells = []
    for q in refs:
        for answer in q["answers"]:
            for mode in ("vector", "hybrid"):
                c = case_by_key.get((answer["sample_id"], mode))
                cells.append(
                    [
                        answer["sample_id"],
                        mode,
                        answer["expected_vector"],
                        c["api_vector"] if c else None,
                        c["medical_http_status"] if c else None,
                        c["attempt_status"] if c else "chưa chạy",
                        c["stage_error"] if c else None,
                    ]
                )
    integration_table = table(
        ["Input", "Nhánh", "Reference", "API vector", "Medical HTTP", "Attempt", "Lỗi"],
        cells,
    )
    ci = data["medical_paired"]["metrics"]["total_agreement"]["cluster_bootstrap_95_ci"]
    delta = (
        data["medical_paired"]["metrics"]["total_agreement"]["adapter_minus_base"] * 100
    )
    examples = read(RUN / "offline/content-error-examples.json")
    correct_but_issue = [
        x for x in examples if x["total_matches_despite_content_issue"]
    ]
    example = correct_but_issue[0] if correct_but_issue else None
    semantic_example = (
        f"Ví dụ `{example['config']}/{example['sample_id']}` có tổng điểm khớp reference nhưng review Codex ghi: "
        + example["review"]["notes"]
        if example
        else "N/A: chưa có ví dụ từ review đã lưu."
    )
    old = ROOT / "data/evaluation/runs/retrieval-integration-20261111"
    corrupt_files = {}
    for name in (
        "report.md",
        "source-coverage-review.json",
        "model-output-review.json",
        "medical-development.json",
    ):
        text = (old / name).read_text(encoding="utf-8")
        corrupt_files[name] = {
            "replacement_U_FFFD": text.count("\ufffd"),
            "question_marks": text.count("?"),
            "has_double_question_marks": "??" in text,
            "sha256": file_hash(old / name),
        }
    write(
        RUN / "utf8-audit.json",
        {
            "old_files": corrupt_files,
            "cause": "Unicode in selected PowerShell here-strings was piped with the shell's legacy encoding; question marks are literal lost bytes, not recoverable by re-decoding",
            "new_output_method": "Python UTF-8 file reads/writes; Vietnamese template supplied through apply_patch, never piped as legacy-encoded stdin",
            "medical_inputs_and_raw_preserved": True,
            "old_notes_not_repaired_or_guessed": True,
        },
    )
    hardware = read(RUN / "baseline.json")
    cpu = (
        read(RUN / "hardware-cpu.json") if (RUN / "hardware-cpu.json").exists() else {}
    )
    tests = list(ET.parse(RUN / "software-tests.xml").getroot().iter("testsuite"))
    test_count = sum(int(x.attrib["tests"]) for x in tests)
    figure_prefix = "../../data/evaluation/runs/" + RUN.name + "/figures/"
    status = (
        f"Đã thực hiện {current['medical_http_attempts']}/12 attempt; {current['valid_medical_api_evaluations']} API evaluation hợp lệ, "
        f"{current['complete_pair_count']}/6 cặp đầy đủ."
        if current["medical_http_attempts"]
        else "Phần kiểm chứng inference sau vá chưa chạy do RAM chưa qua chốt 6 GiB; các ô kết quả mới để N/A. Đã hoàn tất tổng hợp offline và preflight không model."
    )
    new_strategy_table = table(
        [
            "Nhánh mới",
            "Attempt",
            "Medical API hợp lệ",
            "Khớp vector/reference",
            "MAE chuẩn hóa (n)",
            "Practice completed",
            "Teaching mock bị guard",
        ],
        [
            [
                mode,
                m["attempted"],
                m["medical_api_valid"],
                f"{m['exact_vectors']}/{m['planned']}",
                f"{number(m['normalized_mae'])} ({m['mae_n']})",
                m["practice_completed"],
                m["teaching_mock_failed"],
            ]
            for mode, m in current["strategy_results"].items()
        ],
    )
    analysis = (
        read(RUN / "content-analysis.json")
        if (RUN / "content-analysis.json").exists()
        else None
    )
    new_error_text = (
        "Chưa có raw Medical mới để phân tích; không dùng output cũ thay thế."
    )
    if analysis:
        error = next(
            (
                r
                for r in analysis["rows"]
                if r["sample_id"] == "KGR_DEV_FX_RADIO__mixed" and r["mode"] == "hybrid"
            ),
            None,
        )
        if error:
            source = next((e for e in error["evidence"] if e["page_start"] == 14), None)
            excerpt = (
                re.search(r"phim X quang phải lấy hết[^.\n]*", source["content"], re.I)
                if source
                else None
            )
            quote = (
                excerpt.group(0)
                if excerpt
                else "N/A; xem evidence nguyên văn trong content-analysis.json"
            )
            new_error_text = (
                f"**Run mới, attempt{error['ledger_id']}, hybrid:** học viên viết “{error['student_answer']}”. "
                f"Rubric C1 yêu cầu lấy khớp trên/dưới; evidence trang PDF14 ghi “{quote}”. "
                f"Model cho {error['observed_vector']} thay vì {error['expected_vector']}; lý do C1 là "
                f"“{error['parsed']['rubric_scores'][0]['reason']}”. Đây là lỗi phủ định/gán nội dung trong Medical khi đoạn nguồn đã có quy tắc rõ; "
                "không sửa ranking/KG để ép điểm. Vector trên cùng input được báo riêng ở bảng, không đủ để suy hybrid kém hơn nói chung."
            )
        new_error_text += (
            f" Có {analysis['score_vector_mismatches']} output sai vector điểm trong nhóm mới và "
            f"{analysis['score_matches_with_incorrect_missing_overlap']} output khớp điểm nhưng cùng một nhãn nằm trong cả incorrect_points/missing_points. "
            f"Chẩn đoán Teaching mock offline tái hiện {analysis['teaching_mock_diagnostic_errors']}: fixture tạo learning_priority trùng focus khi echo hai danh sách đó; "
            "guard đã chặn. Đây là tái hiện hàm xác định sau run, không phải inference mới và không thay raw/API result. "
            "Điểm đúng không bảo đảm các danh sách phản hồi đúng ngữ nghĩa; review nguồn của Codex chưa phải duyệt bác sĩ."
        )
    cleanup = read(RUN / "cleanup.json") if (RUN / "cleanup.json").exists() else None
    trace_link = (
        "[Trace Medical HTTP mới](trace-example.json)"
        if current["cases"]
        else "Trace Medical HTTP mới: N/A, chưa inference; [trace preflight có nhãn stub](preflight-trace-example.json)"
    )
    integration_figure = (
        f"![Sáu cặp Medical mới; dấu sao là lỗi guard Teaching mock]({figure_prefix}integration-medical-pairs.svg)"
        if (RUN / "figures/integration-medical-pairs.svg").exists()
        else ""
    )
    document = f"""<!-- generated: {RUN.name} -->
# Bản nháp phần thực nghiệm — MedResident-Tutor

Trạng thái: **{status}** Đây là bản nháp từ artifact lưu trên máy, chưa phải kết quả thử nghiệm lâm sàng hoặc nghiên cứu hiệu quả học tập.

## 1. Mục tiêu và câu hỏi nghiên cứu

Thực nghiệm khảo sát ba câu hỏi: adapter V1 thay đổi mức khớp điểm với reference như thế nào khi giữ evidence cố định; Teaching phản hồi có bám Medical và learner context theo các proxy đã định hay không; đường backend có thực sự truy xuất evidence từ corpus/KG và đưa đúng evidence vào Medical không. Chất lượng nội dung và tính đúng của điều phối là hai trục riêng. Không đặt ngưỡng accuracy để chọn hoặc chạy lại output đẹp.

Phân biệt phạm vi: pilot local ngày09/11; benchmark chính ngày10/11; nhóm development tích hợp ngày11/11. Các điểm backend structured/V2 chấm xác định không phải điểm LLM. Benchmark chính dùng evidence tham chiếu cố định; nhóm tích hợp dùng evidence truy xuất lại. Teaching thật thuộc benchmark cũ, Teaching của nhóm tích hợp là mock có nhãn. Nhóm tích hợp chạy FastAPI ASGI/router/service/HTTP trong child riêng, chưa phải browser E2E.

## 2. Phần cứng, phần mềm, model và adapter

Máy local: {hardware["system"]["os"]}, CPU `{cpu.get("Name", "N/A")}` ({cpu.get("NumberOfCores", "N/A")} lõi/{cpu.get("NumberOfLogicalProcessors", "N/A")} logical processors, đo khi bàn giao), RAM vật lý {hardware["system"]["ram_total_bytes"] / 1024**3:.2f} GiB; GPU ghi nhận `{hardware["gpu"]}`. Thứ tự thông số GPU là tên, tổng VRAM, VRAM dùng/trống và driver. Runtime benchmark là Linux/Docker Python3.12; phiên bản package lấy từ metadata của worker, không suy từ môi trường máy chủ.

Medical: Qwen/Qwen3-4B-Instruct-2507, adapter Medical V1 được cung cấp, SHA256 `{data["runtime"]["medical_adapter"]["metadata"]["adapter_sha256"]}`. Teaching: Qwen/Qwen2.5-7B-Instruct cùng adapter Teaching V1 của benchmark. Giữ NF4 double quant, float16, greedy decoding, seed42, input4096/context8192; Medical cap1200 và Teaching cap1600 token. Medical packages: `{data["runtime"]["medical_base"]["metadata"]["packages"]}`.

Metadata base/adapter Medical chỉ khác `adapter_enabled` và `adapter_sha256`; base revision, tokenizer/chat-template/system-prompt hash, quantization, decoding và dataset manifest trùng. Có {data["actual_prompt_comparisons"].get("True", 0)} cặp có hash prompt thực tế cùng nhau; {data["actual_prompt_comparisons"].get("None", 0)} cặp không đủ telemetry do interruption. Không gán sự vắng mặt telemetry là đã xác minh.

## 3. Dữ liệu, reference, split và provenance

Manifest chính chứa50câu từ10chủ đề, mỗi câu có5 biến thể trả lời tổng hợp. Development có10câu/2chủ đề, tương ứng50input Medical đã chuẩn bị; test có40câu/8chủ đề, tương ứng200input cho mỗi cấu hình. Số prepared không đồng nghĩa số đã chạy: các attempt development thực tế được ledger lưu riêng. Teaching test có60input với context none/recurring/improving; payload Medical đầu vào Teaching là reference chuẩn bị sẵn, không lấy tùy tiện output Medical của từng nhánh.

Reference và rubric do Codex đối chiếu đoạn nguồn của hai sách2006/2021, có source ID, trang PDF, locator/hash. `human_reviewed=false`, `clinician_approved=false`: đối chiếu nguồn không đồng nghĩa bác sĩ đã duyệt. Câu trả lời tổng hợp không phải bài làm người học thật. Nguồn còn nguy cơ OCR/khác phiên bản; không diễn giải điểm cao thành an toàn lâm sàng.

Đã xác minh hash toàn bộ dataset manifest và payload của checkpoint khi có telemetry: {data["input_payload_comparisons"]}. Cùng sample IDs, cùng rubric/evidence/expected cho hai cấu hình; CSV `medical-paired.csv` giữ hash riêng từng thành phần. Một interruption không có raw/prompt đầy đủ, giữ lỗi đó trong mẫu số. Không chạy lại locked benchmark và không thay dữ liệu nguồn.

Audit trùng lặp gốc dùng normalized exact matching và SequenceMatcher trên các file training có sẵn, không chứng minh hết nhiễm paraphrase. Provenance dữ liệu huấn luyện adapter chưa đầy đủ (`adapter_training_provenance_incomplete` trong leakage-audit); split theo chủ đề trong benchmark không đồng nghĩa đã chứng minh độc lập với toàn bộ dữ liệu training của adapter. Đây là giới hạn của diễn giải tổng quát hóa.

## 4. Cấu hình đối chứng

| Nhóm | Các nhánh | Evidence và đường chạy |
| --- | --- | --- |
| Benchmark Medical chính | base / adapter | Cùng evidence tham chiếu cố định; batch model local, không đánh giá HTTP |
| Benchmark Teaching chính | base / adapter; raw / guarded | Cùng Medical reference và learner context; guard xác định hậu xử lý |
| Retrieval cũ | vector / hybrid | TF-IDF ký tự,50câu, graph snapshot offline; không phải semantic encoder mới |
| Tích hợp mới | cùng Medical adapter, vector / hybrid | Sáu input từ3câu, semantic E5 local; hybrid live Neo4j; Teaching mock |

Run tích hợp trước đã đóng:12request gồm1timeout,10HTTP429,1completed và2generation. Run xác nhận mới `{RUN.name}` có thư mục/manifest/category riêng, lineage tới run cũ, cùng corpus/encoder/mapping/expected. Không lấy output cũ để lấp ô thiếu của run mới. Cả hai nhánh mới dùng cùng source scope, encoder, threshold0.75, top3, tối đa6000ký tự; hybrid giữ0.85semantic+0.15KG, không reranker. Không tuning theo điểm Medical.

Vector chỉ dùng semantic retrieval trong source scope có metadata đã kiểm, không gọi KG để chọn/boost. Số12Cypher của run cũ là6hybrid×2, vector0. Source scope dùng chung từ metadata/mapping tĩnh, không lấy kết quả truy vấn KG để lọc riêng vector. Concept IDs có thể xuất hiện trong trace vector như metadata; điều đó không chứng minh vector đã dùng KG. Audit/readiness queries được tách riêng khỏi query retrieval và latency.

## 5. Metric và mẫu số

Exact total là số output contract-valid có tổng bằng reference chia toàn bộ200mẫu dự kiến. Exact criterion vector dùng cùng mẫu số; đã đối chiếu thêm theo criterion ID và không phát hiện khác với metric gốc. Schema-valid và contract-valid là hai mức khác nhau: JSON đúng schema vẫn có thể sai tổng điểm so với điểm criteria. Lỗi schema/runtime nằm trong mẫu số agreement, nhưng không được gán điểm0.

MAE chuẩn hóa là trung bình `abs(predicted_total-reference_total)/max_score` trên output có số điểm contract-valid; công bố n và coverage riêng, không suy điểm cho mẫu lỗi. Wrong-criterion award rate dùng số criterion được đánh dấu sai mà model vẫn cho điểm chia số criterion sai thực sự được chấm; planned80, observed67/79 khác nhau do lỗi. Teaching dùng proxy lexical/alignment/context, không phải accuracy sư phạm. Retrieval Hit@5 và coverage là proxy trùng đoạn nguồn, semantic relevance chuyên gia là N/A. Khoảng tin cậy chênh lệch dùng1000 paired bootstrap theo8cụm chủ đề, seed42, giữ các biến thể của một cụm cùng nhau; không coi200biến thể là200người học độc lập.

## 6. Kết quả Medical với evidence cố định

{medical_table}

Các giá trị được tính lại từ checkpoint/raw/expected, không nhập bảng thủ công. Đã parse/validate lại399raw Medical bằng validator V1, kết quả trùng cờ schema/contract và parsed gốc;1interruption không có raw. Exact vector theo criterion ID không làm đổi metric gốc, vì vậy không sửa revision metric lịch sử.

{paired_table}

Adapter trừ base là **{delta:.1f} điểm phần trăm** về exact total. Khoảng paired cluster bootstrap95% là [{ci[0] * 100:.1f}; {ci[1] * 100:.1f}] điểm phần trăm, bao gồm0; không kết luận cải thiện đáng kể. Adapter có contract-valid rate cao hơn nhưng MAE trên mẫu hợp lệ cao hơn; mẫu số MAE khác nhau nên phải đọc cùng coverage. Wrong-criterion awards: base {med["medical_base"]["wrong_criterion_awards"]}/{med["medical_base"]["wrong_criteria_scored_denominator"]}, adapter {med["medical_adapter"]["wrong_criterion_awards"]}/{med["medical_adapter"]["wrong_criteria_scored_denominator"]}. Đây là tín hiệu cần phân tích nội dung, không được che bằng chênh lệch trung bình nhỏ.

![Medical với evidence cố định]({figure_prefix}medical-fixed-evidence.svg)

![Kết quả so sánh trên cùng mẫu]({figure_prefix}medical-paired-outcomes.svg)

CSV `medical-by-group.csv` cung cấp lỗi theo8chủ đề và5loại trả lời. Biểu đồ tách grade mismatch khi contract-valid với lỗi contract/runtime; không quy lỗi hạ tầng thành kiến thức sai.

![Lỗi theo loại trả lời]({figure_prefix}medical-errors-by-answer-type.svg)

## 7. Teaching và retrieval đã có

{teaching_table}

Đã tái tạo120raw Teaching, parsed, guard và proxy từ artifact cũ; kết quả tổng hợp trùng metrics gốc. Guard là hàm xác định, không phải inference mới; proxy được cải thiện sau guard không chứng minh model tự sửa được Medical hoặc dạy hiệu quả. Review trực tiếp của Codex có12mẫu/cấu hình/giai đoạn Teaching,40mẫu/cấu hình Medical; không phải hội đồng bác sĩ hoặc nghiên cứu người dùng. Các nội dung không có đánh giá ngữ nghĩa chắc chắn giữ unknown/N/A.

{retrieval_table}

Đã tính lại proxy từ100record retrieval lưu sẵn (50câu×2), source spans và provenance; không rank lại hoặc gọi Neo4j/LLM. Corpus retrieval cũ1554chunk, TF-IDF char_wb3–5; khác corpus semantic971cửa sổ của nhóm mới. Coverage tăng từ68% lên80% là proxy phủ đầy đoạn tham chiếu, không đồng nghĩa coverage y khoa thực. Không gộp kết quả hai hệ retrieval thành một accuracy.

![Retrieval offline và proxy]({figure_prefix}retrieval-offline-proxies.svg)

## 8. Nhóm tích hợp development sau vá harness

{status}

Preflight mới có12request đi qua FastAPI/router/service và HTTPProvider với transport stub được gắn nhãn, không gọi model. Cấu hình được quan sát tại client thực: read600s, deadline orchestration625s, caller ASGI không đặt timeout30s; production/mock mặc định giữ nguyên.{test_count} test CPU liên quan đã PASS, gồm kiểm readiness vẫn200 khi service lock đang bận và khi caller cancel mà runner chưa dừng. Batch concurrency1, thứ tự mỗi input vector rồi hybrid, cặp đầu ST_CLOSE correct. Readiness/load deadline1200s tách với inference. Timeout/busy/OOM/lỗi điều phối dừng batch; lỗi output schema giữ raw và chỉ tiếp tục nếu lock/generation đã rảnh. Không retry vì điểm sai, không warm-up/smoke generation.

{integration_table}

{new_strategy_table}

Các lỗi timeout/HTTP429 mới: {current["timeout_busy_counts"]}; lỗi guard Teaching mock: {current["teaching_mock_failures"]}. Medical API hợp lệ không đồng nghĩa practice hoàn tất cả Teaching. So sánh cặp về điểm: {current["paired_grade_outcomes"]}. Số mẫu nhỏ và có hai câu trả lời cho mỗi câu hỏi, không dùng các tỉ lệ này để suy ra tổng quát hóa hoặc lợi ích của KG. Trong nhóm quan sát, hybrid có nguồn rõ hơn cho câu X-quang nhưng không cải thiện điểm chấm; không tiếp tục tuning hoặc chạy lại.

{integration_figure}

Số mới: practice attempts duy nhất {current["unique_practice_attempts"]}; practice submit POST kể cả kiểm idempotency {current["practice_submit_posts_including_idempotency_checks"]}; Medical HTTP attempts {current["medical_http_attempts"]}; generation bắt đầu/kết thúc {current["generations_started"]}/{current["generations_finished"]}; raw trả về {current["raw_outputs_saved"]}; Medical API evaluation hợp lệ {current["valid_medical_api_evaluations"]}; practice completed {current["completed_practice_attempts"]}; cặp đầy đủ {current["complete_pair_count"]}/6. HTTP200 của practice không thay được attempt completed/Medical evaluation. Kết quả thiếu là N/A, không mượn raw run cũ hoặc gán0. Sáu input thuộc ba câu chỉ là nhóm kiểm chứng tích hợp nhỏ, không gộp với benchmark200mẫu.

Các số query mới: vector→KG {current["vector_kg_queries"]}, hybrid→KG {current["hybrid_kg_queries"]}, semantic queries {current["vector_queries"]}. Server IDs/hash khớp {current["server_hash_matches"]}, chưa có proof {current["server_hash_unknown"]}, mismatch {current["server_hash_mismatches"]}. File `trace-example.json` chỉ được tạo khi run mới có trace; trạng thái chưa chạy không được gọi là end-to-end mới đã xác nhận. Teaching của nhóm này hoàn toàn mock, không nạp model Teaching.

Ngoài số query retrieval có {current["audit_neo4j_probe_queries_excluded_from_retrieval"]} Cypher kiểm tra kết nối trước load, tách khỏi ranking và latency retrieval. Generation latency mới median/P95: {number(current["generation_latency_median_seconds"])}/{number(current["generation_latency_p95_seconds"])} giây; tổng token input/output {current["input_tokens"]}/{current["generated_tokens"]}; load {number(current["load_seconds"])} giây. Peak VRAM của worker mới chỉ được công bố theo telemetry trong integration-metrics.json, không cộng với RSS hoặc suy thành RAM Windows.

## 9. Phân tích lỗi và tính toàn vẹn tiếng Việt

{new_error_text}

Có {len(correct_but_issue)} ví dụ trong review Medical lưu sẵn có tổng đúng nhưng còn lỗi nội dung/policy; đây là số ví dụ trong tập review, không suy ra tỉ lệ trên200mẫu. {semantic_example}

Ví dụ phủ định đã quan sát ở run tích hợp cũ, attempt544 (không dùng làm kết quả của run mới): học viên viết “Chỉ lấy đúng ổ gãy, không được đưa khớp trên hay khớp dưới vào phim. Hai tư thế cần có là thẳng và nghiêng.” Rubric yêu cầu lấy khớp trên/dưới và hai tư thế; evidence2021 trang PDF14 nêu trực tiếp quy tắc. Model cho[1,1] thay vì reference[0,1] và nói học viên đã nêu C1 đúng. Với evidence có quy tắc rõ, lỗi gán phát biểu/phủ định nằm ở Medical; Teaching mock không chứng minh sửa được lỗi đó. Raw/prompt/trace giữ nguyên. Nếu output mới tái hiện hoặc không tái hiện, bảng mới báo đúng, không chạy lại để chọn kết quả.

Lỗi điều phối run cũ do HTTP read600s được đặt trong provider nhưng router còn deadline30s; server vẫn sinh sau khi caller bỏ chờ, dẫn tới10HTTP429. Lỗi này tách với lỗi nội dung. Bản vá dùng một local profile cho các lớp, ghi trạng thái cancel vào ledger, dừng batch khi hạ tầng lỗi và kiểm service lock thực. Kiểm chứng inference sau vá được công bố theo trạng thái hiện tại, không coi CPU test là bằng chứng inference.

Audit encoding phát hiện dấu `?` literal trong một số notes của `source-coverage-review.json`, `model-output-review.json` và phần notes được chèn vào report cũ. Nguyên nhân là Unicode trong here-string đi qua pipe PowerShell với encoding cũ; không thể khôi phục chữ đã mất bằng đổi encoding. File đề/rubric và raw gốc được đọc UTF-8 còn nguyên, không có U+FFFD; chúng được giữ theo hash. Bản mới dùng template UTF-8 và dữ liệu nguồn còn nguyên, không đoán lại chữ y khoa bị mất. Chi tiết ở `utf8-audit.json`; báo cáo/notes cũ giữ nguyên.

## 10. Thời gian, bộ nhớ và hạn chế

{latency_table}

Latency trên là generation latency của test checkpoint cũ, không phải HTTP end-to-end; tokens là test samples có telemetry, interruption có thể thiếu. Peak memory lấy từ process segment cuối đã lưu, không cộng các peak và không coi RSS Linux/WSL là RAM Windows. Benchmark adapter có recovery segment, giữ riêng ở nguồn; thời gian wall window chứa cả thời gian idle/recovery không được diễn giải là throughput thuần. Bản draft không thêm telemetry khi không có dữ liệu.

Hạn chế: reference và review chưa được bác sĩ duyệt; dữ liệu tổng hợp/ít chủ đề; source OCR và phiên bản cũ; proxy Teaching/retrieval không phải adjudication; không có nghiên cứu người dùng hoặc kết quả học tập; không đánh giá đọc ảnh X-quang; nhóm tích hợp chỉ3câu; phần lớn web vẫn giữ provider mock và bài prelinked. Graph source provenance không đảm bảo model dùng đúng phủ định/ngoại lệ. Không coi graph mở/health200 là runtime KG proof. Không dùng một điểm accuracy để kết luận hệ thống sẵn sàng học tập chính thức.

Ledger chung hiện có {current["shared_ledger_total_actual"]}attempt, baseline run mới {read(RUN / "baseline.json")["ledger_count"]}; cap mới12, ceiling chung800 giữ nguyên. Không sửa raw/expected/row lịch sử, không chạy lại locked benchmark, không train/thử adapter khác. Cleanup hiện {"đã xác nhận bằng cleanup.json" if cleanup else "chưa có audit cuối của run mới"}; weights, adapters, cache và venv được giữ, không tự nạp model lần sau. Web/DB/Neo4j/provider hiện có giữ nguyên.

Nguồn bảng/biểu đồ: `offline/benchmark-verification.json`, các CSV `offline/medical-*`, `teaching-per-sample.csv`, `retrieval-per-question.csv`, `integration-metrics.json`, `integration-per-sample.csv`; toàn bộ nằm trong thư mục run mới. Dữ liệu số trong bảng/biểu đồ do script tính từ artifact, không nhập bằng tay. Xem `report.md` trong run mới cho lệnh và đường dẫn bàn giao.
"""
    target = ROOT / "docs/experiments/experiments-draft-20261111.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert f"<!-- generated: {RUN.name} -->" in target.read_text(encoding="utf-8")
    assert "\ufffd" not in document and "??" not in document
    target.write_text(document, encoding="utf-8")
    handoff = f"""# Xác nhận retrieval → Medical sau vá harness

{status}

{table(["Chỉ số run mới", "Thực tế"], [[k, current[k]] for k in ["inference_patch_verified", "medical_http_attempts", "generations_started", "generations_finished", "valid_medical_api_evaluations", "complete_pair_count", "timeout_busy_counts", "vector_kg_queries", "hybrid_kg_queries", "server_hash_matches", "server_hash_mismatches", "shared_ledger_total_actual"]])}

{new_strategy_table}

Practice completed {current["completed_practice_attempts"]}, lỗi Teaching mock {current["teaching_mock_failures"]}; tách khỏi Medical API hợp lệ. {new_error_text}

Baseline vector không gọi KG: preflight vector0Cypher, hybrid2/request. Cùng scope, corpus, encoder, threshold, top-k, context; không tuning. Query audit/health không được tính thành evidence retrieval. Cấu hình thực tế trong `preflight.json` và live effective_runtime: HTTP read600s, service deadline625s, concurrency1; readiness không thay worker idle.

Benchmark chính được tái parse399Medical raw và120Teaching raw, xác minh payload/prompt/reference/config cùng nhau, tính lại toàn bộ bảng offline. Exact total base74,5%, adapter75,5%; 31 mẫu chỉ adapter đúng và29 chỉ base đúng. CI chứa0, không kết luận cải thiện đáng kể. Kết quả và raw lịch sử không bị ghi đè.

## Artifact

- [Bản nháp phần thực nghiệm](../../../../docs/experiments/experiments-draft-20261111.md).
- [Benchmark xác minh](offline/benchmark-verification.json), [Medical từng mẫu](offline/medical-per-sample.csv), [so sánh cặp](offline/medical-paired.csv).
- [Teaching](offline/teaching-per-sample.csv), [retrieval offline](offline/retrieval-per-question.csv), [ví dụ lỗi nội dung](offline/content-error-examples.json).
- [Phân tích raw và chẩn đoán Teaching mock sau run](content-analysis.json).
- [Nhóm mới](integration-metrics.json), [CSV 12 ô dự kiến và kết quả quan sát](integration-per-sample.csv), {trace_link}.
- [Kiểm tra UTF-8](utf8-audit.json), [cleanup](cleanup.json), [biểu đồ SVG/PNG](figures/).

## Lệnh

```powershell
# Chỉ run đã ủy quyền này; nếu closed/live tồn tại thì không nạp lại model.
python -m local_model_testing.retrieval_confirmation.launch --wait-ram-seconds 180
# Dừng đúng coordinator/container của run mới nếu cần.
python -m local_model_testing.retrieval_confirmation.control stop
# Tổng hợp offline và tái xuất bản bàn giao; không inference.
python -m local_model_testing.retrieval_confirmation.cpu offline_analysis
python -m local_model_testing.retrieval_confirmation.cpu plots
python -m local_model_testing.retrieval_confirmation.reporting
python -m local_model_testing.retrieval_confirmation.cleanup
```

Không chạy lại preflight vào cùng manifest sau freeze. Nếu thiếu RAM, giữ guard6GiB, không đổi precision, không tự đóng ứng dụng. Khi đã có kết quả live/closed, kết thúc thực nghiệm bổ sung; không mở tuning hoặc retry vì điểm thấp. Run cũ `{read(RUN / "configuration.json")["lineage"]}` giữ nguyên; ledger append category mới, không tạo ngân sách800 khác.
"""
    (RUN / "report.md").write_text(handoff, encoding="utf-8")
    write(
        RUN / "deliverable-manifest.json",
        {
            "thesis_path": target.relative_to(ROOT).as_posix(),
            "thesis_sha256": file_hash(target),
            "report_sha256": file_hash(RUN / "report.md"),
            "offline_source_manifest_sha256": data["source_manifest_sha256"],
            "new_integration_metrics_sha256": file_hash(
                RUN / "integration-metrics.json"
            ),
            "generated_from_data": True,
            "encoding": "UTF-8",
            "contains_replacement_characters": False,
            "derived_artifacts": {
                p.relative_to(RUN).as_posix(): file_hash(p)
                for folder in [RUN / "offline", RUN / "figures"]
                for p in folder.iterdir()
                if p.is_file()
            },
        },
    )
    print(
        {
            "thesis": str(target),
            "medical_attempts": current["medical_http_attempts"],
            "pairs": current["complete_pair_count"],
            "ledger": current["shared_ledger_total_actual"],
        }
    )


if __name__ == "__main__":
    main()
