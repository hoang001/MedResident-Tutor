"""Supplement report from saved trace/payload/HTTP/ledger artifacts, no inference."""

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter

from . import ledger
from .common import ROOT, RUN, PARENT, read, write


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *("| " + " | ".join(str(v) for v in row) + " |" for row in rows),
        ]
    )


def counts(cases, controls=()):
    traces = [c["attempt"]["retrieval"] for c in cases] + [c["trace"] for c in controls]
    return {
        "neo4j_cypher_requests": sum(t.get("neo4j_queries", 0) for t in traces),
        "semantic_vector_queries": sum(t.get("vector_queries", 0) for t in traces),
        "strategies": dict(Counter(t["effective_strategy"] for t in traces)),
    }


def main():
    pre = read(RUN / "preflight.json")
    live = read(RUN / "live.json") if (RUN / "live.json").exists() else None
    data = ledger.attempts()
    new = [r for r in data if r["category"] == "medical_retrieval_supplement"]
    reference = read(RUN / "medical-development.json")
    expected = {
        a["sample_id"]: a["expected_vector"] for q in reference for a in q["answers"]
    }
    cases = []
    actual_hash_checks = []
    for c in live.get("cases", []) if live else []:
        result = c["attempt"]
        trace = result["retrieval"]
        trace_id = trace["trace_id"]
        raw_path = RUN / "raw" / (trace_id + ".json")
        tokens_path = RUN / "token-traces" / (trace_id + ".json")
        request_path = RUN / "requests" / (trace_id + ".json")
        raw = read(raw_path) if raw_path.exists() else None
        token = read(tokens_path) if tokens_path.exists() else None
        request = read(request_path) if request_path.exists() else None
        matched = (
            (
                raw["evidence_at_http_server"] == trace["selected_evidence"]
                and raw["input_payload_sha256"] == request["payload_sha256"]
            )
            if raw and request
            else None
        )
        actual_hash_checks.append(matched)
        pred = result.get("medical_evaluation")
        spec = next(q for q in reference if q["question_id"] == trace["question_id"])
        score_by_id = (
            {s["criterion_id"]: s["score"] for s in pred["rubric_scores"]}
            if pred
            else {}
        )
        vector = (
            [score_by_id[c["criterion_id"]] for c in spec["rubric"]["criteria"]]
            if pred
            else None
        )
        try:
            raw_scores = (
                json.loads(raw["raw"]["text"]).get("rubric_scores", []) if raw else []
            )
        except (ValueError, TypeError, AttributeError):
            raw_scores = []
        raw_by_id = {s["criterion_id"]: s["score"] for s in raw_scores}
        record = next(
            r
            for r in new
            if r["sample_id"] == c["sample_id"]
            and r["config"] == "retrieval_medical_" + c["mode"] + "_v1"
        )
        reason = json.loads(record["reason"]) if record.get("reason") else {}
        cases.append(
            {
                "sample_id": c["sample_id"],
                "mode": c["mode"],
                "trace_id": trace_id,
                "expected_vector": expected[c["sample_id"]],
                "actual_vector": vector,
                "late_raw_vector_not_returned_to_practice": [
                    raw_by_id[c["criterion_id"]] for c in spec["rubric"]["criteria"]
                ]
                if raw
                and not pred
                and all(
                    c["criterion_id"] in raw_by_id for c in spec["rubric"]["criteria"]
                )
                else None,
                "model_http_status": 200
                if record["status"] == "completed"
                else reason.get("http_status"),
                "raw_inference_seconds": raw["raw"]["inference_seconds"]
                if raw
                else None,
                "expected_total": sum(expected[c["sample_id"]]),
                "actual_total": pred["total_score"] if pred else None,
                "exact_vector": vector == expected[c["sample_id"]],
                "status": result["status"],
                "stage_error": result.get("stage_error"),
                "effective_strategy": trace["effective_strategy"],
                "neo4j_queries": trace["neo4j_queries"],
                "vector_queries": trace.get("vector_queries", 0),
                "selected_ids": [
                    e["source_unit_id"] for e in trace["selected_evidence"]
                ],
                "selected_pages": [
                    [e["source_id"], e["page_start"]]
                    for e in trace["selected_evidence"]
                ],
                "backend_http_evidence_hash_match": matched,
                "input_tokens": token["input_tokens"] if token else None,
                "generated_tokens": token["generated_tokens"] if token else None,
                "truncated": token["truncated"] if token else None,
                "medical_http_calls": c["provider_calls"]["medical"],
                "teaching_mock_calls": c["provider_calls"]["teaching"],
            }
        )
    suites = list(ET.parse(RUN / "backend-tests.xml").getroot().iter("testsuite"))
    software_tests = {
        key: sum(int(s.attrib.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    metrics = {
        "software_tests": software_tests,
        "software_tests_before_inference": 86,
        "retained_preflight": counts(pre["cases"], pre["controls"]),
        "live": counts(live.get("cases", [])) if live else None,
        "shared_ledger_total": len(data),
        "parent_initial_attempts": read(RUN / "baseline.json")["parent_attempts"],
        "new_attempts": len(new),
        "new_generations_started": sum(r["generation_started"] for r in new),
        "new_attempt_statuses": dict(Counter(r["status"] for r in new)),
        "model_http_statuses": dict(
            Counter(str(c["model_http_status"]) for c in cases)
        ),
        "practice_medical_errors": dict(
            Counter(c["stage_error"]["code"] for c in cases if c["stage_error"])
        ),
        "supplement_closed_no_more_inference": len(new) == 12,
        "resume_readonly_neo4j_probe_queries": read(RUN / "resume-neo4j-probe.json")[
            "cypher_probe_requests"
        ]
        if (RUN / "resume-neo4j-probe.json").exists()
        else 0,
        "evidence_server_hash_checks": {
            "matched": sum(v is True for v in actual_hash_checks),
            "unknown": sum(v is None for v in actual_hash_checks),
            "mismatch": sum(v is False for v in actual_hash_checks),
        },
        "cases": cases,
    }
    mapping = []
    for mode in ("vector", "hybrid"):
        group = [r for r in cases if r["mode"] == mode]
        metrics[mode] = {
            "planned": 6,
            "attempted": len(group),
            "contract_valid": sum(r["actual_vector"] is not None for r in group),
            "exact_vector": sum(r["exact_vector"] for r in group),
            "truncated": sum(bool(r["truncated"]) for r in group),
        }
        for r in group:
            mapping.append(
                [
                    r["sample_id"],
                    mode,
                    r["expected_vector"],
                    r["actual_vector"],
                    r["model_http_status"],
                    r["status"],
                    r["stage_error"],
                ]
            )
    identity = []
    for sid in expected:
        pair = [r for r in cases if r["sample_id"] == sid]
        if len(pair) == 2:
            identity.append(
                {
                    "sample_id": sid,
                    "same_evidence_ids": pair[0]["selected_ids"]
                    == pair[1]["selected_ids"],
                    "both_api_evaluations_available": all(
                        r["actual_vector"] is not None for r in pair
                    ),
                    "same_actual_vector": pair[0]["actual_vector"]
                    == pair[1]["actual_vector"]
                    if all(r["actual_vector"] is not None for r in pair)
                    else None,
                }
            )
    metrics["retrieval_pair_comparison"] = identity
    write(RUN / "supplement-metrics.json", metrics)
    if cases:
        with (RUN / "medical-retrieved-per-sample.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
            writer.writeheader()
            for row in cases:
                writer.writerow(
                    {
                        k: json.dumps(v, ensure_ascii=False)
                        if isinstance(v, (list, dict))
                        else v
                        for k, v in row.items()
                    }
                )
    phase = (
        f"Đã ghi nhận {len(cases)} lượt Medical HTTP bổ sung; {metrics['new_generations_started']} generation bắt đầu"
        if new
        else "Audit/retrieval đã xong; chưa có inference Medical HTTP bổ sung"
    )
    old = read(PARENT / "metrics.json")["medical"]
    old_table = table(
        ["Nhóm cũ, evidence tham chiếu cố định", "Final n", "Exact total"],
        [
            [c, m["planned"], f"{m['exact_total_score_agreement']:.3f}"]
            for c, m in old.items()
        ],
    )
    new_table = table(
        [
            "Nhóm bổ sung",
            "Dự kiến/request/API hợp lệ",
            "Khớp vector/API hợp lệ",
            "Token cap",
        ],
        [
            [
                mode,
                f"6/{m['attempted']}/{m['contract_valid']}",
                f"{m['exact_vector']}/{m['contract_valid']}"
                if m["contract_valid"]
                else "N/A",
                m["truncated"],
            ]
            for mode in ("vector", "hybrid")
            for m in [metrics[mode]]
        ],
    )
    by_sample = table(
        [
            "Sample ID",
            "Evidence",
            "Expected",
            "Medical actual",
            "Medical HTTP",
            "Status",
            "Error",
        ],
        mapping,
    )
    request_table = table(
        [
            "Đợt lưu được đầy đủ",
            "Neo4j Cypher thực",
            "Semantic vector query",
            "Medical generation",
        ],
        [
            [
                "Preflight 15 đề ×2 + controls",
                metrics["retained_preflight"]["neo4j_cypher_requests"],
                metrics["retained_preflight"]["semantic_vector_queries"],
                0,
            ],
            [
                "Medical HTTP bổ sung",
                metrics["live"]["neo4j_cypher_requests"] if live else 0,
                metrics["live"]["semantic_vector_queries"] if live else 0,
                metrics["new_generations_started"],
            ],
        ],
    )
    cleanup = read(RUN / "cleanup.json") if (RUN / "cleanup.json").exists() else None
    cleanup_text = (
        "Đã kiểm tra worker/container thoát, cổng model trống, RAM/VRAM sau dừng, service gốc giữ nguyên; xem cleanup.json."
        if cleanup
        else "Chưa có audit cleanup cuối; không tuyên bố đã giải phóng worker của phần bổ sung."
    )
    ram_failure = (
        read(RUN / "startup-ram-failure.json")
        if (RUN / "startup-ram-failure.json").exists()
        else None
    )
    runtime_limit = (
        f"**Medical HTTP chưa được kiểm chứng:** checkpoint loading bị chốt RAM dừng trước readiness; "
        f"RAM trống thấp nhất {ram_failure['minimum_host_available_bytes'] / 1024**2:.0f} MiB, "
        "ba mẫu liên tiếp dưới 512 MiB. Không gửi request chấm, không tiêu attempt. "
        "Lỗi chính: `RuntimeError: Sustained host memory guard; no requests submitted`. "
        "Cleanup gặp race Docker `--rm` giữa ps/inspect (`CalledProcessError`); đã kiểm riêng bằng đúng CID, "
        "không dừng service khác. Log và RAM samples được lưu nguyên ở các file `startup-ram-failure-*`. "
        "Lệnh launch tiếp theo yêu cầu ít nhất **6 GiB RAM Windows trống** (mức dự phòng, không đảm bảo mọi tải khác), "
        "giữ nguyên cấu hình model/retrieval đã khóa. Cần đóng bớt ứng dụng nặng trước khi chạy; không tự dừng web/DB/Neo4j."
        if ram_failure and not new
        else ""
    )
    live_summary = (
        "**Lượt nạp sau khi giải phóng RAM đã thành công, nhưng so sánh model bị lỗi điều phối.** "
        "12 request đã dùng hết cap bổ sung: 1 lần deadline practice30s, 10 HTTP429 `PROVIDER_BUSY`, "
        "1 HTTP200 đi hết practice/Teaching mock. Chỉ2 `model.generate` bắt đầu, đều có raw/EOS; "
        "kết quả vector đầu tiên về muộn sau32,924s nên không thành API success. "
        "Hybrid cuối cùng trả grade nhưng có lỗi nội dung [1,1] so với reference [0,1]. "
        "Không có cặp sample với hai API evaluation thành công; không kết luận accuracy hay hybrid tốt hơn. "
        "Đã đóng run, không retry hoặc dùng thêm inference dù ledger chung còn dưới800."
        if new
        else ""
    )
    source_review = (
        read(RUN / "source-coverage-review.json")
        if (RUN / "source-coverage-review.json").exists()
        else None
    )
    source_table = (
        table(
            ["Đề", "Nhánh", "Nguồn hỗ trợ C1/C2", "Đối chiếu văn bản"],
            [
                [
                    r["question_id"],
                    r["mode"],
                    r["source_support_by_criterion"],
                    r["notes"],
                ]
                for r in source_review["records"]
            ],
        )
        if source_review
        else "Chưa có đối chiếu coverage độc lập với output model."
    )
    output_review = (
        read(RUN / "model-output-review.json")
        if (RUN / "model-output-review.json").exists()
        else None
    )
    output_notes = (
        "\n".join("- " + s for s in output_review["findings"])
        if output_review
        else "Chưa có review output Medical bổ sung; không suy kết quả model từ retrieval preflight."
    )
    available_cases = live.get("cases", []) if live else pre["cases"]
    example = (
        next(
            c
            for c in available_cases
            if c["mode"] == "hybrid" and c["attempt"].get("medical_evaluation")
        )
        if any(
            c["mode"] == "hybrid" and c["attempt"].get("medical_evaluation")
            for c in available_cases
        )
        else next(c for c in available_cases if c["mode"] == "hybrid")
    )
    trace = example["attempt"]["retrieval"]
    request = (
        read(RUN / "requests" / (trace["trace_id"] + ".json"))
        if (RUN / "requests" / (trace["trace_id"] + ".json")).exists()
        else None
    )
    example_data = {
        "question_id": trace["question_id"],
        "trace": trace,
        "source_provenance": example["attempt"]["provenance"],
        "actual_medical_http_payload_sha256": request["payload_sha256"]
        if request
        else None,
        "medical_stage": example["attempt"]["provider_metadata"].get("medical"),
    }
    write(RUN / "trace-example.json", example_data)
    text = f"""# Nối retrieval → Medical: kiểm chứng bổ sung ngày 11/11/2026

**{phase}.** Đây là kiểm chứng tích hợp nhỏ; không phải benchmark accuracy mới hay chứng nhận lâm sàng.

{runtime_limit}

{live_summary}

## 1. Trả lời trực tiếp về web và KG

1. Web chính vẫn giữ provider mock và chế độ evidence mặc định **prelinked**. Nộp bài ở cấu hình đó không truy vấn KG.
2. Code mới khi bật `PRACTICE_RETRIEVAL_STRATEGY=hybrid` cho câu hỏi sách có phạm vi nguồn hợp lệ: `PracticeBookRetriever.retrieve` gọi `Neo4jEvidenceRepository.lookup`. Truy vấn chỉ đọc seed ID (tối đa3) và một hop (tối đa24 cạnh), lấy `content[].sources`/`edge.sources`. Không giả KG có Document/SourceUnit, không import hoặc đổi ontology.
3. Source resolver nối provenance đến văn bản corpus; ranking chọn bundle. `practice.submit` đưa chính bundle vào snapshot Medical, `process` kiểm lại IDs/hash, HTTP provider dùng trace UUID. `medical_server` kiểm payload/hash evidence tại HTTP trước `PilotRunner.generate`.
4. CASE01/XR01 V1 vẫn dùng SourceUnits gắn sẵn từ case/annotation ngoài hai sách. Bài V2 structured vẫn chấm xác định, không model. Câu không có phạm vi sách đã xác minh không tự bị nối vào KG. Mapping hiện có gồm15 đề development và một đề sách đã nhập; không suy học phần từ tên course.
5. KG trong kiểm chứng hybrid chính là **live Neo4j**; văn bản/semantic index là snapshot nguồn local. Offline graph chỉ được bật rõ bằng cấu hình riêng. Teaching trong kiểm chứng là mock, có metadata, không nạp model Teaching. API `/rag` tổng quát cũ vẫn mock và không được dùng làm bằng chứng của đường practice mới.

## 2. Trước và sau

| Thành phần | Trước | Sau, opt-in |
| --- | --- | --- |
| Question/rubric | PostgreSQL | PostgreSQL giữ nguyên |
| Evidence | Reader join RubricCriterionSourceUnit → SourceUnit | Prelinked cũ hoặc semantic/hybrid bundle thật |
| KG lúc nộp bài | Không | Bounded read-only lookup trong retriever |
| Semantic search | Mock; benchmark cũ TF-IDF offline riêng | Encoder CPU local + cosine trên source corpus |
| Snapshot/history | Payload/provenance gắn sẵn | Thêm trace, candidates, IDs/hash, source edition/pages, fallback |
| Medical/Teaching web | Mock | Không đổi mặc định; child test Medical HTTP thật/Teaching mock |

Các hàm chính: `reader.question_rubric` đọc đề/rubric không lấy gold evidence; `practice.service.submit` chọn strategy và tạo snapshot; `PracticeBookRetriever.retrieve`/`Neo4jEvidenceRepository.lookup` lấy candidate; `BookIndex.resolve` nối provenance đến văn bản; `verify_payload_evidence` bảo vệ IDs/hash trước HTTP; `practice.service.process` chạy Medical rồi tạo Teaching payload từ đánh giá Medical và rubric, learner context hiện rỗng/taxonomy chưa gắn. Teaching mock chỉ thay bước phản hồi trong phép thử, vẫn qua validator/guard và snapshot như đường practice.

```mermaid
flowchart LR
  Q[PostgreSQL Question và Rubric] --> S{{Source strategy}}
  S -->|prelinked / external case| P[PostgreSQL SourceUnits]
  S -->|book hybrid| C[Versioned concept mapping]
  C --> K[Neo4j read-only 1 hop]
  K --> R[Resolve source references]
  S -->|book vector| V[Local semantic source index]
  V --> B[Rank và bound context]
  R --> B
  P --> SS[Snapshot evidence và trace]
  B --> SS
  SS --> M[Medical HTTP / adapter giữ nguyên]
  M --> T[Teaching mock có nhãn]
```

## 3. Nguồn, truy xuất và giới hạn

| Chế độ | Nguồn và cách lấy | Medical |
| --- | --- | --- |
| prelinked | PostgreSQL SourceUnits đã gắn vào rubric/bài | Theo provider cấu hình |
| vector | Semantic cosine trên văn bản hai sách local | Evidence retrieval được đưa vào snapshot |
| kg_lookup | Mapping ID → KG provenance; chỉ xếp hạng văn bản resolve được từ KG, có ngưỡng semantic | Thiếu nguồn trả insufficient; không tự lấy gold |
| hybrid | Union candidate vector/KG, boost theo source support | Fallback vector có nhãn nếu KG không đóng góp |
| offline graph | Cùng resolver nhưng graph export có hash, nhãn offline_snapshot | Không tính là live Neo4j |
| mock | Chỉ provider trả dữ liệu giả; retrieval thật/fake được ghi riêng | Teaching kiểm chứng luôn mock |

`data/retrieval/book-corpus-v1/` có971 cửa sổ nguồn từ hai sách, dùng679 trang đối chiếu sẵn khi có, còn lại OCR/transcription nguồn đã có. Không chạy OCR/extraction, không chèn câu trả lời giả lập/expected. Source manifest giữ hash, trang, edition và phiên bản văn bản; không gộp triple thành một khẳng định mới. Giữ cửa sổ nguyên văn khi đưa vào prompt; không cắt cuối evidence để vừa context.

Encoder mới chỉ phục vụ retrieval CPU: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), revision/hash trong encoder manifest. Query/passage prefixes, masked mean/L2; đoạn dài dùng cửa sổ token chồng lặp rồi tổng hợp vector, không âm thầm bỏ phần cuối. Không thay Medical/Teaching model hay adapter. Cả hai nhánh dùng cùng corpus/index, top3, context tối đa6000ký tự, threshold.75; hybrid candidate union/boost .85semantic+.15KG, không reranker. Tham số chốt trước Medical, không chỉnh theo điểm model.

Retriever chỉ nhận đề, question identity và source/concept metadata đã biên soạn. Không nhận student answer, rubric, expected hay gold evidence IDs. Mapping dùng ID và trích nguồn đã kiểm; query hash chống dùng lại ID cho đề khác. Tham chiếu nguồn trong mapping phục vụ kiểm toán, không được đưa vào query/ranking.

Nonempty top-k không được đánh dấu là evidence đủ về y khoa: bundle là `retrieved_unadjudicated`. Thiếu phạm vi nguồn, không có candidate qua ngưỡng, index không đọc được → `insufficient_evidence`, stage_error rõ, không gọi Medical. Không có concept hoặc Neo4j lỗi có thể fallback vector nếu source scope hợp lệ; không tính lượt đó là hybrid có KG thành công. Nguồn không đọc được ghi unresolved reference, không tự thay gold.

## 4. Kiểm chứng không model

Preflight đi qua actual FastAPI router/service/auth, actual PostgreSQL transaction rollback và source index/Neo4j thật. 15 đề ×2 nhánh; learner GET không lộ rubric/expected/annotation. Snapshot/detail/history và idempotency kiểm bằng request thật trong ASGI child; không phải browser E2E. Medical/Teaching ở giai đoạn này đều mock có nhãn.

Controls lưu riêng: Neo4j connection failure thực; ngoài source scope không có evidence; câu sách chưa có concept mapping fallback vector; offline graph có nhãn; hai ca ngoài sách prelinked; API thiếu evidence có0provider calls. Unit fake kiểm logic concept không sources, source locator hỏng và tamper hash; không coi fake là truy vấn KG thành công.

Trước inference có **86 software tests PASS**. Sau khi phát hiện và sửa lỗi harness, `backend-tests.xml` ghi **{software_tests["tests"]} kiểm thử**, {software_tests["failures"]} failures, {software_tests["errors"]} errors; bản86 giữ tại `before-timeout-fix-backend-tests.xml`. Đây là software tests, không phải số mẫu model. `payload-token-audit.json` chứng minh 12 payload từ backend retrieval đã qua validator và tokenizer CPU, tối đa 2995 token, không truncation, 0 generation. Các payload này chỉ là kết quả retrieval đóng băng để so hash; live vẫn truy xuất lại, không dùng file kế hoạch để thay evidence.

## 5. Medical HTTP thật: nhóm bổ sung

Ba đề development (phần mềm2006, mỏm cụt2006, Xquang gãy xương2021), mỗi đề một câu đúng và một câu có đúng/sai, cùng sample IDs ở hai nhánh. Không đọc hoặc sửa final test để debug. Ref do Codex đối chiếu nguồn; chưa user/clinician duyệt. Medical chỉ nhận văn bản, không đọc ảnh.

Giữ Medical Qwen3-4B-Instruct-2507 + adapter đã cung cấp, prompt/validator V1, NF4/float16, greedy/seed42, cap1200, input4096/context8192. Dùng service HTTP gốc và `HTTPProvider`, thực thi từ practice app mới trong child riêng; web port8000/provider hiện có không đổi. Không retry hoặc smoke. Raw/tokens/server payload giữ kể cả output sai hay contract lỗi.

Nhóm cũ (khác tập câu, giữ nguyên kết quả lịch sử):

{old_table}

Nhóm bổ sung nhỏ, không gộp accuracy với nhóm cũ:

{new_table}

{by_sample}

HTTP status ở bảng/CSV là Medical HTTP, tách với practice POST (HTTP200 vẫn có thể chứa `medical_failed`). Request đầu không nhận được Medical HTTP response trước deadline nên status là null;10request sau có HTTP429; request cuối HTTP200. Late raw của attempt533 có vector[1,1] nhưng không được trả vào practice, không tính là API evaluation thành công. Điểm thiếu do hạ tầng là N/A, không được coi là model chấm sai. Chưa có cặp sample đầy đủ để so vector/hybrid.

Lỗi do harness: HTTPProvider được đặt local read600s riêng nhưng router/service vẫn nhận settings mặc định deadline30s. Sau khi run thoát, đã giữ manifest và toàn bộ input/code thực thi theo hash tại `frozen-inputs/`, rồi sửa riêng harness: cùng local profile cho router và HTTP (deadline625s), ghi ledger failed khi coroutine bị cancel, dừng batch ngay khi Medical lỗi. Ba regression test mới + các test cũ đều PASS; chưa kiểm chứng bản vá bằng inference vì cap12 đã dùng hết. `post-run-harness-fix.json` ghi revision/hash trước/sau, không giả rằng bản sửa đã được dùng cho run này. Attempt533 được đối soát terminal failed có raw về muộn; chỉ cập nhật row mới của supplement, giữ nguyên532row cũ.

Ledger chung hiện có **{metrics["shared_ledger_total"]}attempts**, trước bổ sung532; mới **{metrics["new_attempts"]}/12**, generate bắt đầu **{metrics["new_generations_started"]}**. Không tạo ngân sách800 mới. Hash old rows và old artifacts được kiểm lại riêng. Không sửa raw hoặc chấm lại để ép điểm theo expected.

## 6. Trace và số request

{request_table}

Đếm Neo4j là số `tx.run` Cypher của lookup, không đếm healthcheck/handshake; connection failure control có thể0Cypher dù đã thử kết nối. Vector query là query embedding/cosine, khác971passage embeddings khi dựng index. Số trên thuộc lần preflight được lưu đầy đủ và phần live; các lần CPU debug trước đó không có telemetry tổng toàn phiên nên không gộp thành một con số network total giả. Model attempts được ledger chung đếm toàn bộ, không bỏ lỗi.

Ngoài bảng runtime có2Cypher audit schema ban đầu và1Cypher probe khi tiếp tục sau giải phóng RAM (`resume-neo4j-probe.json`); các probe đó không chứng minh evidence được đưa vào Medical. Có2chuỗi hash được đối chiếu tại server của2generation;10HTTP429 không có generation/server evidence capture, không tính là proof Medical nhận bundle.

Ví dụ `trace-example.json`: question `{trace["question_id"]}` → curated IDs `{trace["concept_ids"]}` → KG source candidates → ranked source IDs `{[e["source_unit_id"] for e in trace["selected_evidence"]]}` → payload Medical. `evidence_server_hash_checks` trong supplement-metrics.json: {metrics["evidence_server_hash_checks"]}. Chỉ có check tại HTTP server mới chứng minh nội dung tới Medical thật, không dùng việc Neo4j đang chạy làm bằng chứng.

Hai phương pháp có thể trả cùng evidence hoặc không cải thiện điểm. Xem `retrieval_pair_comparison` và CSV từng mẫu; không kết luận hybrid tốt hơn chỉ do có thêm evidence. Lỗi nội dung/điểm khi evidence đúng được giữ là lỗi Medical; không chỉnh retrieval sau model.

Đối chiếu coverage trước khi xem output model, chỉ là đọc nguồn của Codex, chưa có bác sĩ duyệt (`None` = cần duyệt phạm vi, không phải chứng minh thiếu hoàn toàn):

{source_table}

Nhận xét output sau chạy:

{output_notes}

## 7. Cấu hình / chạy lại

Default `PRACTICE_RETRIEVAL_STRATEGY=prelinked`; opt-in `vector`, `kg_lookup`, `hybrid`. `PRACTICE_RETRIEVAL_GRAPH=neo4j` hoặc `offline`; corpus/encoder/mapping/snapshot path là cấu hình backend, không lấy từ người học. Optional backend extra `[retrieval]` cần torch/transformers/numpy; main image hiện tại không được rebuild trong kiểm chứng.

```powershell
# Run hiện đã đóng: lệnh sau chỉ xác nhận giữ kết quả, không nạp model/gọi thêm.
python -m local_model_testing.retrieval_integration.launch --wait-ram-seconds 0
# Stop đúng worker/child/coordinator của task; không dừng web/DB/Neo4j.
python -m local_model_testing.retrieval_integration.control stop
# Kiểm tra/dọn CID đúng worker nếu Docker --rm đã tự xóa container.
python -m local_model_testing.retrieval_integration.owned_cleanup
python -m local_model_testing.retrieval_integration.finish
python -m local_model_testing.retrieval_integration.report

# Opt-in deployment riêng sau khi review; KHÔNG được tự áp dụng trong task này:
docker compose -f docker-compose.yml -f compose.retrieval.yml up -d --build backend
```

Override build chỉ cài retrieval extra/bật retrieval; provider/model-call lock vẫn theo cấu hình gốc. Không tự chuyển web sang model thật. Run/config/manifest bổ sung ở folder mới; old benchmark/report không ghi đè, chỉ ledger được append theo ủy quyền. Manifest đã frozen không được sửa để giả cache tương thích.

Không chạy lại `preflight` vào cùng folder sau khi đã freeze: file kết quả là đầu vào manifest. Đợt mới cần run/config/manifest mới và ủy quyền cap mới; vẫn dùng ledger chung hiện tại, không reset800. Bản vá harness chỉ được software-test; không tự chạy lại mẫu sai hoặc timeout. Trước khi có live result, `launch` kiểm dependency/RAM rồi khởi động coordinator một lần; hiện run đã đóng nên launcher trả về ngay. Đã gặp một lần startup thiếu dependency và một lần memory guard, đều0inference; giữ logs cũ, không đổi prompt/retrieval.

Dependency điều phối Windows đã cài riêng vào `controller-deps`, không đổi Python/venv inference. Nếu chuyển máy, chuẩn bị bằng `python -m pip install --target data/evaluation/runs/retrieval-integration-20261111/controller-deps httpx==0.28.1`. `launch` cần 6 GiB RAM trống trước khởi động; coordinator/model vẫn giữ các guard gốc. Không có model worker nào tự chạy lại sau khi lệnh kết thúc.

## 8. Cleanup và hạn chế

{cleanup_text}

Các SourceUnits/corpus vẫn có nhiễu OCR/khác phiên bản; cosine/graph support không thay adjudication đủ căn cứ theo criterion. Source windows có thể chưa phủ mọi điều kiện dù không bị cắt khi gửi. Ref/quality chưa được chuyên gia độc lập duyệt. Mapping nhỏ, không tự bao phủ toàn ngân hàng. Không phải end-to-end browser UI, không phải đánh giá ảnh hay tác động học tập. Teaching mock chỉ chứng minh plumbing. Không thay ontology, import KG, sửa database chính, VPN/route hoặc commit/push.
"""
    (RUN / "report.md").write_text(text, encoding="utf-8")
    (ROOT / "docs/retrieval-medical-integration-20261111.md").write_text(
        "# Retrieval → Medical: kiểm chứng bổ sung\n\n" + phase + ".\n\n"
        "[Báo cáo và lệnh chạy](../data/evaluation/runs/retrieval-integration-20261111/report.md).\n\n"
        "[Trace ví dụ](../data/evaluation/runs/retrieval-integration-20261111/trace-example.json).\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "report": str(RUN / "report.md"),
                "new_attempts": len(new),
                "shared_attempts": len(data),
            }
        )
    )


if __name__ == "__main__":
    main()
