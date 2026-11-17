"""Generate thesis tables/figures and a Markdown draft from metric files, never hand-enter results."""
import csv
import json

from .common import DATA, ROOT, RUN, read, rows


def fmt(value, digits=3):
    return "N/A" if value is None else f"{value:.{digits}f}"


def table(headers, records):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"]*len(headers)) + " |",
                      *("| " + " | ".join(str(v) for v in row) + " |" for row in records)])


def interpretation(metrics):
    a, b = [metrics["medical"]["medical_"+k] for k in ("base", "adapter")]
    if any(m["attempted"] < m["planned"] for m in (a, b)):
        return "Medical còn mẫu chưa chạy; chưa kết luận đối chứng từ các tỷ lệ đang cập nhật."
    delta = 100*(b["exact_total_score_agreement"]-a["exact_total_score_agreement"])
    vector_delta = 100*(b["exact_criterion_vector_agreement"]-a["exact_criterion_vector_agreement"])
    paired = metrics["medical_paired_comparison"]["metrics"]["total_agreement"]["cluster_bootstrap_95_ci"]
    return (f'Trên cùng test, chênh lệch adapter − base của exact total là {delta:+.1f} '
        f'điểm phần trăm, exact vector {vector_delta:+.1f} điểm phần trăm. Đây là '
        f'so sánh mô tả theo reference dự án; CI bootstrap cặp theo chương của '
        f'chênh lệch exact total là [{100*paired[0]:+.1f}; {100*paired[1]:+.1f}] điểm phần trăm '
        '(tám cluster, chưa phải external validation). Không đồng nghĩa cải thiện mọi loại lỗi '
        'hoặc hiệu quả học tập. Cần đọc tỷ lệ cho điểm ý sai, coverage và review '
        'nội dung bên cạnh exact agreement. Một phản hồi có điểm tổng đúng vẫn có '
        'thể chứa ý gán sai cho học viên hoặc nhận xét mâu thuẫn.')


def teaching_interpretation(metrics):
    a, b = [metrics["teaching"]["teaching_"+k] for k in ("base", "adapter")]
    if any(v["raw"]["attempted"] < v["raw"]["planned"] for v in (a, b)):
        return "Teaching còn mẫu chưa chạy; chưa kết luận A/B."
    return (f'Alignment proxy raw base {100*a["raw"]["alignment_proxy_pass_rate"]:.1f}% '
        f'→ adapter {100*b["raw"]["alignment_proxy_pass_rate"]:.1f}%; guarded '
        f'{100*a["guarded"]["alignment_proxy_pass_rate"]:.1f}% → '
        f'{100*b["guarded"]["alignment_proxy_pass_rate"]:.1f}%. Tuy vậy anchor proxy '
        f'raw giảm từ {100*a["raw"]["medical_anchor_proxy_pass_rate"]:.1f}% xuống '
        f'{100*b["raw"]["medical_anchor_proxy_pass_rate"]:.1f}%. Không kết luận adapter '
        'tốt hơn trên mọi thành phần. Một phần output adapter dùng lời nhận xét '
        'ngắn như “Medical Evaluation cho biết”, ít từ khóa factual hơn nên có thể '
        'không qua anchor proxy. Đây là giải thích cần đối chiếu từng output, '
        'không phải lý do tự bỏ metric thấp. Direct review bên dưới vẫn ghi cả '
        'lỗi phân loại lẫn trường hợp đảo ý đúng trong câu hỏi tiếp nối.')


def figures(metrics):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    folder = RUN / "figures"
    folder.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.bbox": "tight"})
    colors = ["#24776d", "#aa593a"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    keys = ["schema_valid_rate_all_planned", "exact_total_score_agreement", "exact_criterion_vector_agreement"]
    for index, config in enumerate(("medical_base", "medical_adapter")):
        vals = [metrics["medical"][config][key] for key in keys]
        ax.bar(np.arange(3)+(index-.5)*.34, vals, width=.34, label=config, color=colors[index])
    ax.set_xticks(np.arange(3), ["Schema", "Exact total score", "Exact score vector"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Rate over all planned final samples")
    ax.legend(frameon=False)
    ax.set_title("Medical: fixed reference evidence (text only)")
    for suffix in ("png", "svg"):
        fig.savefig(folder / ("medical."+suffix), dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labels, values, bars = [], [], []
    for index, config in enumerate(("teaching_base", "teaching_adapter")):
        for stage in ("raw", "guarded"):
            labels.append(config.replace("teaching_", "")+"\n"+stage)
            values.append(metrics["teaching"][config][stage]["alignment_proxy_pass_rate"])
            bars.append(colors[index])
    ax.bar(labels, values, color=bars)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Alignment proxy pass rate (not clinical quality)")
    ax.set_title("Teaching: controlled synthetic Medical/context fixtures")
    for suffix in ("png", "svg"):
        fig.savefig(folder / ("teaching."+suffix), dpi=180)
    plt.close(fig)
    if metrics["retrieval"]:
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        for index, config in enumerate(("vector", "hybrid")):
            vals = [metrics["retrieval"][config][key] for key in ("hit_at_5", "criterion_evidence_coverage_proxy")]
            ax.bar(np.arange(2)+(index-.5)*.34, vals, width=.34, label=config, color=colors[index])
        ax.set_xticks(np.arange(2), ["Hit@5 (source-span rule)", "Full passage coverage proxy"])
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Rate over original queries")
        ax.legend(frameon=False)
        ax.set_title("Offline character TF-IDF vs TF-IDF + exported KG")
        for suffix in ("png", "svg"):
            fig.savefig(folder / ("retrieval."+suffix), dpi=180)
        plt.close(fig)


def main():
    metrics = read(RUN / "metrics.json")
    manifest = read(DATA / "manifest.json")
    configs = metrics["runtime"]
    finished = all(r["process"].get("status") == "finished" for r in configs.values())
    cleanup = read(RUN/"cleanup-integrity.json") if (RUN/"cleanup-integrity.json").exists() else None
    state = ("ĐÃ KẾT THÚC INFERENCE — số liệu sơ bộ theo reference dự án" if finished else
             "ĐÃ DỪNG — có phần lỗi/chưa chạy, báo cáo kết quả một phần" if cleanup else
             "BẢN NHÁP ĐANG CHẠY — bảng hiện tại có mẫu chưa chạy, chưa là kết quả final")
    cleanup_text = (f'Đã kiểm container và coordinator của đợt chạy thoát thật; '
        f'{cleanup["protected_files_unchanged"]} file được bảo vệ giữ hash; '
        f'ba service gốc giữ nguyên ID. Sau cleanup, Windows RAM available '
        f'{cleanup["after_cleanup"]["system"]["ram_available_bytes"]/1024**3:.2f} GiB; '
        f'GPU: `{cleanup["after_cleanup"]["gpu"]}`. Cổng model 8101/8102 không mở; '
        f'web/BE/PG vẫn hoạt động. Xem cleanup-integrity.json.' if cleanup else
        'Chưa chạy audit cleanup cuối: inference/coordinator vẫn có thể đang hoạt động; không tuyên bố đã giải phóng model.')
    figures(metrics)
    med_table = table(["Cấu hình", "Dự kiến/chạy/hợp lệ", "Schema/planned", "Exact total", "Exact vector", "MAE [0,1]", "MAE coverage", "Cho điểm ý sai (n/d)", "Coverage ý sai"], [
        [c, f'{m["planned"]}/{m["attempted"]}/{m["contract_valid"]}', fmt(m["schema_valid_rate_all_planned"]),
         fmt(m["exact_total_score_agreement"]), fmt(m["exact_criterion_vector_agreement"]),
         fmt(m["mae_normalized"]), fmt(m["mae_coverage"]),
         f'{m["wrong_criterion_awards"]}/{m["wrong_criteria_scored_denominator"]} ({fmt(m["wrong_criterion_award_rate"])})', fmt(m["wrong_criterion_coverage"])]
        for c, m in metrics["medical"].items()])
    ci_table = table(["Cấu hình", "Exact total 95% CI", "Exact vector 95% CI", "Cluster"], [
        [c, " – ".join(fmt(v) for v in m["cluster_bootstrap_95_ci"]["total_agreement"]),
         " – ".join(fmt(v) for v in m["cluster_bootstrap_95_ci"]["vector_agreement"]),
         m["cluster_bootstrap_95_ci"]["clusters"]] for c, m in metrics["medical"].items()])
    teaching_table = table(["Cấu hình", "Đầu ra", "N chạy/planned", "Schema", "Alignment proxy", "Context proxy (d)", "Anchor proxy"], [
        [c, stage, f'{m["attempted"]}/{m["planned"]}', fmt(m["schema_valid_rate"]),
         fmt(m["alignment_proxy_pass_rate"]), f'{fmt(m["context_usage_proxy_pass_rate"])} ({m["context_denominator"]})',
         fmt(m["medical_anchor_proxy_pass_rate"])]
        for c, stages in metrics["teaching"].items() for stage, m in stages.items()])
    retrieval_table = table(["Cách", "N query", "Hit@5", "Độ phủ đoạn nguồn proxy", "Semantic coverage", "Median/p95 giây"], [
        [c, m["queries"], fmt(m["hit_at_5"]), fmt(m["criterion_evidence_coverage_proxy"]), "N/A",
         f'{fmt(m["latency_median_seconds"], 5)}/{fmt(m["latency_p95_seconds"], 5)}']
        for c, m in (metrics["retrieval"] or {}).items()])
    runtime_rows = []
    for c, r in configs.items():
        process = r["process"]
        host = RUN / (c + "-host-memory.json")
        available = [s["system"]["ram_available_bytes"] for s in read(host)] if host.exists() else []
        for archived in r.get("archived_host_memory_files", []):
            available += [s["system"]["ram_available_bytes"] for s in read(RUN/archived)]
        runtime_rows.append([c, r["attempts"], r["generation_calls_started"],
            fmt(process.get("load_and_artifact_check_seconds"), 1), fmt(process.get("total_wall_seconds"), 1),
            fmt(r["observed_wall_window_including_recovery_idle_seconds"], 1),
            fmt(process.get("peak_vram_allocated_bytes", 0)/1024**3),
            fmt(process.get("peak_process_rss_bytes", 0)/1024**3),
            fmt(min(available)/1024**3 if available else None)])
    runtime_table = table(["Cấu hình", "Attempts", "Generate started", "Load/verify giây (phiên cuối)", "Wall giây (phiên cuối)", "Cửa sổ wall giây kể cả phục hồi/chờ", "Peak torch VRAM GiB", "Peak Linux RSS GiB", "Min Windows available GiB"], runtime_rows)
    cost_table = table(["Cấu hình", "Raw trả về", "Input token", "Token sinh", "Tổng gen giây", "Median/p95 gen giây", "Cache hit lần cuối", "Phiên bị ngắt lưu riêng"], [
        [c, r["returned_raw_responses"], r["input_tokens_including_development"],
         r["generated_tokens_including_development"], fmt(r["generation_seconds_sum"], 1),
         f'{fmt(r["generation_latency_median_seconds"], 2)}/{fmt(r["generation_latency_p95_seconds"], 2)}',
         r["process"].get("cache_hits", "N/A"), len(r["archived_process_segments"])]
        for c, r in configs.items()])
    leakage = read(DATA / "leakage-audit.json")
    max_sim = max(r["max_question_sequence_similarity"] for r in leakage["rows"])
    error_rows = []
    for c, m in metrics["medical"].items():
        error_rows.append([c, json.dumps(m["error_types"]), m["truncated"], m["not_run"],
                           fmt(m["generation_latency_median_seconds"], 2), fmt(m["generation_latency_p95_seconds"], 2)])
    error_table = table(["Cấu hình", "Loại lỗi", "Truncated", "Chưa chạy", "Median gen s", "p95 gen s"], error_rows)
    review_rows = rows(RUN / "manual-review.jsonl") if (RUN / "manual-review.jsonl").exists() else []
    manual_table_rows = []
    for config, review in metrics["review"].items():
        for stage, values in review["stages"].items():
            for key, measure in values["measures"].items():
                manual_table_rows.append([config, stage,
                    f'{values["n_reviewed"]}/{values["n_planned_for_review"]}; {values["n_with_semantic_assessment"]}', key,
                    f'{measure["n_known"]}/{measure["n_unknown"]}/{measure["n_not_applicable"]}', fmt(measure["mean_or_rate"])])
    manual_table = table(["Cấu hình", "Stage", "Mẫu kiểm/planned; có nhận định nội dung", "Cờ/điểm", "Biết/không rõ/N.A.", "Tỷ lệ/mean"], manual_table_rows)
    quality_table = table(["Cấu hình", "Stage", "Mức0", "Mức1", "Mức2", "Chưa rõ"], [
        [c, stage, *(values["quality_level_counts"].get(str(level), 0) for level in range(3)),
         values["measures"]["quality_level"]["n_unknown"]]
        for c, r in metrics["review"].items() if c.startswith("teaching")
        for stage, values in r["stages"].items()])
    teaching_examples = "\n".join(f'- `{r["config"]}/{r["sample_id"]}` ({r["stage"]}), '
        f'quality={r["quality_level"]}: {r["notes"]}' for r in review_rows
        if r["config"].startswith("teaching") and r.get("quality_level") is not None)
    group_rows = []
    with (RUN/"medical-by-group.csv").open(encoding="utf-8-sig") as stream:
        answer_groups = {}
        for r in csv.DictReader(stream):
            if r["dimension"] == "answer_type":
                answer_groups[(r["config"], r["group"])] = r
            group_rows.append([r["config"], r["dimension"], r["group"],
                r["attempted"]+"/"+r["planned"], fmt(float(r["exact_total_score_agreement"])),
                fmt(float(r["exact_criterion_vector_agreement"]))])
    group_table = table(["Cấu hình", "Nhóm theo", "Nhóm", "Đã chạy/planned", "Exact total", "Exact vector"], group_rows)
    group_analysis = "\n".join(f'- `{kind}`: exact total base '
        f'{100*float(answer_groups[("medical_base", kind)]["exact_total_score_agreement"]):.1f}% → adapter '
        f'{100*float(answer_groups[("medical_adapter", kind)]["exact_total_score_agreement"]):.1f}%, '
        f'mỗi cấu hình {answer_groups[("medical_base", kind)]["planned"]} mẫu. '
        + explanation for kind, explanation in (
            ("full", "Review cho thấy base thường bỏ sót paraphrase, adapter nhận ra nhiều hơn."),
            ("mixed", "Review phát hiện adapter có lúc chép ý đúng từ source dù học viên nêu phủ định/ngược thứ tự; một mẫu adapter bị ngắt runtime vẫn nằm trong mẫu số."),
            ("wrong", "Một số output đúng số 0 vẫn có correct_points trái với nhận xét; contract lỗi không được chữa hoặc loại khỏi exact denominator."),
            ("unrelated", "Điểm tổng đúng không bảo đảm danh sách nhận xét đúng: vẫn có output gắn sở thích ngoài đề vào incorrect_points.")))
    paired_retrieval = metrics.get("retrieval_paired_comparison", {})
    retrieval_analysis = "\n".join(f'- `{key}`: hybrid tăng ở '
        f'{len(change["gained_question_ids"])} query, giảm ở {len(change["lost_question_ids"])} query. '
        f'Query tăng: {", ".join(change["gained_question_ids"]) or "không có"}; '
        f'query giảm: {", ".join(change["lost_question_ids"]) or "không có"}.'
        for key, change in paired_retrieval.items())
    interruptions = [read(p) for p in sorted(RUN.glob("runtime-interruption-*.json"))]
    interruption_text = ("\n".join('- ' + e["cause"] + '. Lỗi gốc: `'
        + "`; `".join(e["original_docker_errors"]) + '`. Không retry generation bị ngắt; '
        'checkpoint và ledger giữ lỗi trong mẫu số. Metadata/RAM của phiên trước '
        'được lưu trong segments trước resume.' for e in interruptions) if interruptions else
        'Không có bản ghi runtime-interruption riêng.')
    token_audit = read(RUN/"token-payload-audit.json")["audit"]
    token_table = table(["Loại", "Input dataset", "Max input token", "Prompt checkpoint đã đối chiếu", "Không có hash prompt", "Mismatch"], [
        [kind, v["inputs"], v["max_input_tokens"], sum(v["actual_checkpoint_prompts_checked"].values()),
         len(v["checkpoints_without_recorded_prompt"]), len(v["prompt_mismatches"])]
        for kind, v in token_audit.items()])
    examples = "\n".join(f'- `{r["config"]}/{r["sample_id"]}` ({r.get("stage", "raw")}): {r["notes"]}'
        for r in review_rows if any(r.get(k) is True for k in ("score_list_contradiction", "attributed_unstated_claim", "incorrect_vs_missing_policy_error", "insufficient_evidence_misinterpreted", "role_violation")))
    text = f'''# Thực nghiệm MedResident Tutor — benchmark mới v1

Ngày 10/11/2026. **{state}**.

## 1. Mục tiêu và câu hỏi nghiên cứu

Đánh giá sơ bộ theo bộ tham chiếu của dự án: adapter Medical cung cấp có cải
thiện chấm tự luận ngắn so với cùng base không adapter không; Teaching adapter
có cải thiện bám evaluation và context không; KG export có bổ sung cho truy xuất
vector offline không. Không đặt điều kiện accuracy phải đạt một ngưỡng để kết
thúc; không suy ra hiệu quả học tập của học viên.

Pilot cũ (09/11), backend chấm xác định structured (10/11), benchmark mới,
Medical với evidence cố định, retrieval và kiểm thử HTTP là các phạm vi riêng.
Benchmark mới không dùng điểm giả lập hay điểm backend để làm output model.

## 2. Môi trường và cấu hình

Môi trường thực tế được ghi ở `baseline.json`, từng `*-process.json` và
`*-host-memory.json`: Windows, Docker Linux CUDA, GPU RTX 5060 8 GiB, RAM vật lý
khoảng 15,76 GiB. Đọc snapshot thật để đối chiếu tài nguyên, không suy từ máy
training. Runtime inference dùng venv Docker đã có, offline; không tải weights.

Medical: Qwen/Qwen3-4B-Instruct-2507. Teaching: Qwen/Qwen2.5-7B-Instruct.
Mỗi loại chạy base thật không PEFT và cùng base gắn adapter người dùng cung cấp.
Manifest/hash gốc được giữ; chưa có chứng chỉ hash lịch sử độc lập cho Medical
V1. Cùng tokenizer base/chat template, NF4 double quant float16, batch size 1,
greedy, seed 42, input tối đa 4096, context 8192. Medical cap 1200 token mới;
Teaching 1600. Không truncate input, không timeout generation, không chọn output
tốt nhất trong nhiều lần. Cấu hình và packages thực tế nằm trong metadata.

Prompt V1, guard V1 và validator V1 giữ nguyên. Metadata fingerprint chuỗi dùng
SHA-256 của canonical JSON; không nhầm với SHA-256 UTF-8 trực tiếp trong báo cáo
pilot. Mỗi checkpoint giữ actual prompt hash, payload hash, EOS/cap và config
fingerprint để chống dùng cache khác cấu hình.

Audit tokenizer chạy CPU sau inference, không load weights hoặc gọi generate.
Tái dựng toàn bộ input, kiểm chuỗi trả lời học viên còn đầy đủ và hash prompt
khớp checkpoint. Lượt Docker bị ngắt không lưu hash prompt nên không tự tuyên
bố đã đối chiếu được lượt đó. Kết quả thực tế:

{token_table}

## 3. Dữ liệu, provenance và gán nhãn

{manifest["questions"]} câu gốc, {manifest["topics"]} chủ đề từ hai sách: vết thương phần mềm,
cắt cụt chi, thần kinh, mạch máu, nối lại chi, khung cố định ngoài, uốn ván,
bánh chè, hoại thư sinh hơi, viêm xương tủy. Mỗi câu hai tiêu chí một điểm và
năm biến thể: đầy đủ diễn đạt khác rubric, đúng một phần, sai một ý trọng yếu,
đúng lẫn sai, ngoài chủ đề. Tổng 250 mẫu giả lập; không phải 250 người học độc lập.

Các câu trả lời, counterclaim và paraphrase được Codex biên soạn thủ công từ
nguồn local, không dùng model đang đánh giá làm đáp án. Hai tiêu chí phản ánh
phạm vi nguồn được chọn, không phải chuẩn đánh giá năng lực BSNT. Một số
counterclaim rõ/đơn giản và câu ngoài chủ đề lặp giữa nhiều đề; cần mở rộng độ
khó, câu trả lời tự nhiên hơn ở nghiên cứu sau.

`provenance.jsonl` có source ID, hash OCR/PDF, trang PDF, offset cửa sổ nguồn,
excerpt và căn cứ từng tiêu chí. Không giả số trang PDF là trang in. Các đoạn
OCR sai nghĩa đưa vào `review-queue.json`; một số đoạn được đọc trực tiếp PDF
và chép tay riêng (2006 trang 46/48, 2021 trang 496), không sửa OCR gốc.
Corpus retrieval chứa toàn bộ cửa sổ OCR sách và các đoạn chép lại từ PDF;
không chứa câu trả lời giả lập, expected hay nhãn benchmark. Corpus vẫn có
nhiễu OCR/caption, được giữ như hạn chế nguồn đầu vào.

Chính sách mới: correct = ý thực sự nêu và có nguồn; incorrect = ý thực sự
nêu và bị nguồn bác bỏ; missing = tiêu chí chưa đề cập. Ý đã đề cập nhưng sai
không đồng thời bị liệt kê là thiếu trong bộ mới. Ngoài chủ đề không được coi
là phát biểu y khoa sai. sufficient_evidence thể hiện đủ căn cứ để chấm, không
phải học viên đúng/sai. Không sửa expected cũ theo chính sách này.

Mức review là **Codex đối chiếu nguồn**, chưa có user review hay clinician approval.
Nhãn này được ghi đúng trong manifest và từng reference. Review HTML chứa cả
source, đề, câu trả lời, expected và output/raw. Sửa nhãn tương lai phải tạo
revision, không âm thầm sửa benchmark đã chạy.

## 4. Chia tập và leakage

Development gồm hai chủ đề (vết thương phần mềm, cắt cụt): 10 câu/50 biến thể;
test gồm tám chủ đề khác: 40 câu/200 biến thể. Mọi câu/biến thể trong cùng chủ
đề/chương được giữ cùng tập, bao gồm các câu gần nhau trên cùng đoạn nguồn.
Không đưa hai bài demo X-quang hay pilot gãy hở đã phân tích nhiều vào test mới.

Đối chiếu toàn bộ file training/validation/test có sẵn không thấy câu hỏi trùng
nguyên văn; max normalized SequenceMatcher similarity là {max_sim:.3f}.
Đây chỉ là kiểm văn bản, không chứng minh không có paraphrase contamination,
không bao phủ dữ liệu pretraining hay đầy đủ lịch sử training của adapter.
Nguồn kiến thức trùng corpus RAG là có chủ đích; nhãn/câu trả lời không vào corpus.
Dataset/split/reference/corpus/graph được hash trước inference ở `manifest.json`.

## 5. Các đối chứng và candidate

Medical A/B chỉ khác việc gắn adapter; cả hai nhận cùng bốn trường, rubric và
evidence tham chiếu cố định. Đây không phải bằng chứng retrieval end-to-end,
không gửi ảnh và không đánh giá năng lực đọc X-quang. Development nhỏ kiểm
payload/format/token và ledger trước final; lỗi model không được chữa.

Teaching A/B có 60 input final: 20 MedicalEvaluation tham chiếu nhất quán,
mỗi evaluation ghép ba context giả lập (trống/lỗi lặp/cải thiện). MedicalEvaluation
không phải output model chưa kiểm, giúp tách nhiễu từ Medical. Context không
phải lịch sử người học thật. Raw và guarded giữ riêng; cùng guard V1 cho A/B.

Mỗi cấu hình Medical gọi bốn mẫu development/smoke, mỗi cấu hình Teaching gọi
hai mẫu development/smoke. Hai đối chứng dự kiến tổng cộng 12 lượt smoke và
520 lượt final. Không gọi toàn bộ 50 biến thể development; chúng vẫn được
lưu riêng trong dataset để kiểm tra và nghiên cứu tiếp.

Không thử candidate/prompt V1.1 trong đợt này: quyết định trước khi xem final,
ưu tiên đối chứng V1 đã định. Không train, chỉnh adapter, prompt hay keyword
chữa điểm; không tuning theo kết quả final.

## 6. Metric và mẫu số

Schema-valid tính riêng schema và contract. Exact total/vector dùng toàn bộ
200 mẫu final mỗi cấu hình, lỗi parse/schema/contract tính không đạt. Nếu còn
chưa chạy, tỷ lệ/planned chỉ là cận dưới theo coverage, không gán lỗi cho model.
MAE = mean(|predicted total-reference total|/max score), chỉ trên output hợp lệ,
công bố n và coverage. Cho điểm ý sai = số criterion reference ghi rõ sai mà
model cho >0 / số criterion sai có output hợp lệ, kèm coverage so với toàn bộ
criterion sai dự kiến; không đánh đồng bỏ trống/ngoài chủ đề với sai y khoa.

Khoảng tin cậy exact agreement dùng 1000 bootstrap theo **nhóm chủ đề/chương**,
giữ nguyên các câu và năm biến thể trong nhóm. Chỉ có tám cluster test nên cần
thận trọng khi diễn giải. Không coi 200 biến thể là 200 câu độc lập.

Teaching schema và alignment/context/anchor dùng proxy V1 đã có; không gọi
proxy là độ đúng chuyên môn. Context usage có mẫu số 40 input có lịch sử, không
trộn 20 context trống. Vi phạm vai trò trong văn xuôi và chất lượng sư phạm
cần direct review; không có nhãn thì N/A. Mẫu review được chọn trước ở split,
cùng IDs cho các đối chứng; raw và guarded phân biệt.

Alignment proxy là AND của chín kiểm tra V1: contract, strengths, corrections,
missing_focus, priority, evidence, cấm field điểm, anchor và context. Hai danh
sách corrections/missing được so Counter chuỗi với Medical; paraphrase đúng
nghĩa vẫn có thể không khớp. Strength/priority và anchor dùng ngưỡng similarity
lexical giữ từ validator cũ; context dựa một phần vào marker như “lặp”, “cải
thiện”. Vì vậy proxy thất bại không tự chứng minh phát biểu y khoa sai; proxy
đạt cũng chưa chứng minh mọi câu trong văn xuôi đúng. Guard là hậu xử lý xác
định, không sinh generation thứ hai và không thay điểm Medical.

Retrieval: 50 câu gốc, một query/đề, không dùng biến thể hay expected/gold IDs
để truy xuất. Offline sparse character TF-IDF cosine so với cùng vectorizer
cộng KG source-page boost từ ba node và một-hop neighbors. Đây không phải
neural embedding/production retriever hoặc live Neo4j. Cùng corpus, top5,
6000 ký tự context, không reranker. Hit@5 yêu cầu ít nhất một chunk riêng lẻ
chứa >=50% đoạn nguồn tham chiếu;
coverage theo criterion dùng đủ toàn đoạn tham chiếu hỗ trợ criterion, hợp
nhất span chồng lặp. Hai tiêu chí thường dùng chung đoạn. Đây là **proxy
bao phủ nguồn bảo thủ**, không phải nhãn đủ căn cứ y khoa từng ý được chuyên
gia adjudicate. Semantic criterion coverage để N/A. Không tạo số liệu relevance giả.

## 7. Kết quả đo thực tế

### Medical — evidence cố định

{med_table}

![Medical](figures/medical.png)

{ci_table}

{interpretation(metrics)}

### Teaching — fixture kiểm soát

{teaching_table}

![Teaching](figures/teaching.png)

{teaching_interpretation(metrics)}

### Retrieval offline

{retrieval_table}

![Retrieval](figures/retrieval.png)

{retrieval_analysis}

KG source-page boost có thể đưa thêm đoạn lân cận vào context và tăng độ phủ
đoạn nguồn, trong khi vector đã lấy được một chunk trúng nên Hit@5 không đổi.
Đây là diễn giải theo cơ chế và các ranking lưu lại, không chứng minh quan hệ
KG đã cải thiện hiểu biết y khoa hay semantic relevance. Giữ nguyên corpus,
context cap và query; không chỉnh boost theo kết quả test.

Bảng theo chủ đề và loại trả lời ở `medical-by-group.csv`; từng mẫu ở
`medical-per-sample.csv`, `teaching-per-sample.csv`. Tất cả bảng và hình được
sinh từ metrics JSON/checkpoint, không nhập tay để làm đẹp báo cáo.

## 8. Phân tích lỗi và review nội dung

{error_table}

Mẫu Medical review được chốt 40 ID, phân bố đủ tám chủ đề và năm loại trả lời;
không trộn phát hiện ngoài mẫu vào tỷ lệ. Người review là Codex, không chuyên
gia. Teaching chọn trước 12 ID và kiểm raw/guarded riêng; rubric chất lượng:
0 = đảo evaluation/bịa chuyên môn hoặc lịch sử; 1 = bám anchor nhưng chung
chung/thiếu hướng dẫn; 2 = bám anchor, đề xuất hành động học cụ thể và dùng
context đúng. Không coi rubric agent review là bằng chứng lâm sàng độc lập.

Số output đã review và mẫu số theo từng cờ ở `metrics.json` mục review.
Với cờ nhị phân, mean là tỷ lệ cờ=true trong các đánh giá biết rõ; quality_level
là điểm trung bình 0–2, không phải tỷ lệ accuracy. Unknown loại khỏi mẫu số và
được công bố. Quy ước không double-list ý sai thành thiếu là lựa chọn vận hành
của benchmark, không phải chân lý lâm sàng; cần tách mismatch quy ước này khỏi
lỗi gán ý cho học viên hoặc phủ định sai. Diễn giải lỗi point-list theo source
và ngữ cảnh, không dùng matching từ khóa để thay agent review.

Trong review Teaching, role_violation gồm việc tự chuyển hoặc thêm nhãn
đúng/sai/thiếu trái MedicalEvaluation đã cung cấp. Cờ này không chỉ biểu thị
bịa kiến thức y khoa; lỗi double-list sai/thiếu là mismatch quy ước vận hành,
không được diễn giải thành tỷ lệ phát biểu y khoa sai trên lâm sàng.

Context trống là N/A cho cờ dùng lịch sử trong direct review, được tách khỏi
nhận định chưa rõ. Mức chất lượng không xuất hiện trong output thực tế có số
lượng 0; không biên soạn thêm output mẫu để lấp mức còn thiếu.

{manual_table}

{quality_table}

Kết quả theo nhóm (cùng số liệu trong CSV):

{group_analysis}

{group_table}

Một số ví dụ có lỗi đã đọc trực tiếp (giữ nguyên output):

{examples or "Chưa có annotation nội dung hoàn tất; không suy ra semantic PASS từ schema hoặc score."}

Ví dụ Teaching theo mức chất lượng (raw/guarded tách riêng, chỉ trong mẫu chốt):

{teaching_examples or "Chưa đủ output Teaching để review nội dung."}

## 9. Chi phí, bộ nhớ, độ ổn định và cleanup

Tổng attempt ghi ledger: **{metrics["execution_attempts"]}**, generate call bắt đầu:
**{metrics["generation_calls_started"]}**. Trần toàn đợt 800, Medical final 400,
Teaching final 120, development 40. Load/khởi động không phải generation.
Lỗi request đã reserve vẫn tính ngân sách; không retry vì model sai. Output
không hợp lệ giữ nguyên và tiếp tục các mẫu độc lập; OOM/runtime lặp thì dừng sạch.

{runtime_table}

{cost_table}

Chi phí token/gen ở bảng trên tính cả smoke và final từ từng checkpoint một
lần, không cộng raw và guarded như hai generation. Nếu có phiên ngắt, load/wall
và peak torch/RSS ở bảng runtime là phiên cuối; các phiên trước ở `segments/`.
Min Windows available lấy cả các phiên đã lưu. Lượt ngắt không trả raw có token,
thời gian sinh và peak không đo xong nên không suy đoán hoặc cộng số giả.
Cửa sổ wall tính từ snapshot trước load đầu tiên tới snapshot sau container
cuối thoát, gồm thời gian gián đoạn/phục hồi. Toàn cửa sổ chạy model (baseline
tới after-experiment, không gồm chuẩn bị dataset) là
**{fmt(metrics["model_experiment_wall_window_seconds"], 1)} giây**; nếu còn chạy
thì N/A. Không cộng raw/guarded hay cộng thời gian load như generation.

{interruption_text}

RSS đo trong process Linux, torch allocated là VRAM tensor, không tương đương
toàn bộ bộ nhớ GPU hay toàn PC. Windows RAM available đo từ host mỗi 20 giây;
baseline/after có GPU/process list thực tế. Token, median/p95, wall và shard
checkpoint đã lưu; thời gian load/hash nêu riêng, không giấu vào latency generation.

`empty-api-rejection.json` ghi HTTP 422 với câu trả lời rỗng ở API web hiện có,
0 generation. Đây chỉ là kiểm input validation, **không chạy model HTTP E2E**
trong đợt mới. Các kiểm thử phần mềm runner/metric không phải mẫu đánh giá model.

Controller chỉ dừng container có CID/label/project đúng ownership, chờ thoát
rồi mới ghi after-container-exit và đo bộ nhớ. Không chỉ empty_cache để kết luận
đã giải phóng model. Giữ nguyên web/BE/PG/Neo4j/provider, không import dữ liệu
benchmark vào DB hay mastery. Giữ weights/adapter/cache/venv; không autostart.

{cleanup_text}

## 10. Hạn chế và hướng cải thiện

Bộ tham chiếu tổng hợp, nguồn sách/phiên bản cụ thể và Codex source-check chưa
thay người dùng hay chuyên gia; không đánh giá phân bố bài làm thực, không
đánh giá tác động học tập. False/mixed và off-topic có mẫu dễ/khá lộ; mỗi câu
hai tiêu chí, chưa phủ đầy đủ kỹ năng BSNT. Không kết luận model đủ dùng cho
chấm chính thức chỉ vì schema tốt hoặc score agreement cao.
Agent biên soạn nguồn/tham chiếu cũng thực hiện direct review và biết tên cấu
hình; review chưa độc lập hoặc làm mù. Cần reviewer khác đối chiếu để đánh giá
thiên lệch và độ nhất quán giữa người chấm.

Medical chỉ đánh giá văn bản với gold reference evidence. Retrieval offline
lexical/KG và source-span qrels chưa thay neural/live retrieval hay clinical
relevance annotation. KG export có thể còn lỗi/thiếu cạnh và OCR còn nhiễu;
không sửa ontology để tối ưu điểm. Nếu hybrid không tăng Hit@5, cần phân tích
query/entity linking/context coverage chứ không tuyên bố KG luôn hiệu quả.

Teaching fixture có Medical nhất quán và đủ evidence; chưa mô phỏng mọi lỗi
Medical thực tế hay tình huống evidence thiếu. 20 evaluation hiện đều có một
ý đúng và một ý sai/thiếu, tổng 1/2; chưa phủ evaluation toàn đúng/toàn sai
trong phép thử Teaching riêng. Proxy có giới hạn lexical/context-marker và
không bao phủ mọi vi phạm trong văn xuôi. Máy còn phục vụ ứng dụng và tác vụ
nền nên latency là đo trên PC dùng chung, không phải microbenchmark cô lập. Runtime quantized
trên 8 GiB GPU có thể khác môi trường training. Cần clinician review, câu trả
lời thật, relevance labels và external validation ở nghiên cứu sau.

Hệ thống backend chấm cấu trúc vẫn là luồng dùng được không phụ thuộc model;
output tự luận/model nên được trình bày là tham khảo nếu chất lượng chưa đủ.

## Tái lập / resume / stop

```powershell
# Không tạo lại dataset đã đóng băng. Mặc định dùng cùng run/budget/checkpoint.
.\\.venv-local-models\\Scripts\\python.exe -m local_model_testing.experiment.control run --config all
.\\.venv-local-models\\Scripts\\python.exe -m local_model_testing.experiment.control stop

# Tính lại offline từ raw/checkpoint; không phát sinh generation.
python -m local_model_testing.experiment.metrics
& "$env:TEMP/medresident-cases-venv/Scripts/python.exe" -m local_model_testing.experiment.report
python -m local_model_testing.experiment.review

# Nếu người dùng sửa nhãn sau review: giữ v1, cung cấp file reference revision mới.
# Ghi vào offline-rescores/<revision>, không gọi model hoặc sửa metric gốc.
python -m local_model_testing.experiment.rescore --reference <reference-moi.jsonl> --revision reference-v2
```

File raw/parsed/errors/checkpoint và execution ledger ở
`data/evaluation/runs/{RUN.name}/`; dataset/reference/split/hash ở
`data/evaluation/medresident-benchmark-v1/`. Mở `review.html` trong run để duyệt.
Run đã hoàn tất được reuse không nạp lại model; checkpoint cùng ID khác config
fingerprint bị từ chối. Attempt bị ngắt không âm thầm chạy lại khi resume.
Không đổi run ID để reset ngân sách; dataset được gắn một execution run.
Không commit/push Git.
'''
    (RUN / "report.md").write_text(text, encoding="utf-8")
    pointer = ROOT / "docs/benchmark-experiment-20261110.md"
    pointer.write_text('# Thực nghiệm benchmark mới — 10/11/2026\n\n' + state + '\n\n'
        + f'Báo cáo sinh từ metric: [report.md](../data/evaluation/runs/{RUN.name}/report.md).\n\n'
        + f'Review: [review.html](../data/evaluation/runs/{RUN.name}/review.html).\n\n'
        + 'Không trộn kết quả pilot, structured backend, retrieval và chất lượng model. '
        + 'Đây là reference sơ bộ được Codex đối chiếu nguồn, chưa có chuyên gia duyệt.\n', encoding="utf-8")
    print(json.dumps({"report": str(RUN / "report.md"), "inference_finished": finished}))


if __name__ == "__main__":
    main()
