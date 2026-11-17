"""Render local author/research review; no model calls and no output repair."""
import argparse
import html
import json
import os

from .common import DATA, ROOT, RUN, read, rows


def e(value):
    return html.escape(str(value), quote=True)


def render():
    references = {r["sample_id"]: r for r in rows(DATA / "medical-reference.jsonl")}
    samples = rows(DATA / "medical-inputs.jsonl")
    reviews = rows(RUN/"manual-review.jsonl") if (RUN/"manual-review.jsonl").exists() else []
    pdfs = {r["source_id"]: r["repo_relative_path"]
            for r in read(ROOT/"data/knowledge-extraction/inventory.json")["documents"]}
    parts = ['<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Benchmark research review</title>',
        '<style>body{font:16px/1.6 Arial,sans-serif;color:#18312d;background:#f7faf9;max-width:1150px;margin:auto;padding:24px}article{border-top:1px solid #cbdad7;padding-block:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}summary{cursor:pointer;padding:12px 0}a{color:#116c60}blockquote{margin-inline:0;padding:12px;background:white}p{max-width:75ch}summary:focus-visible,a:focus-visible{outline:3px solid #116c60}</style>',
        '<h1>Review benchmark mới — đối chiếu nguồn và output thật</h1><p>50 câu gốc, 10 chủ đề. Câu trả lời giả lập và fixture Teaching được biên soạn cho nghiên cứu; không phải bài làm người học thật. Codex đối chiếu nguồn, chưa được người dùng hoặc chuyên gia duyệt. Không trộn điểm structured backend/pilot cũ vào kết quả model.</p>',
        '<p>Raw và parsed được giữ nguyên. Bộ tham chiếu/split đã đóng băng. Sửa nhãn về sau phải tạo revision mới, giữ lịch sử output. Các tỷ lệ proxy không phải chứng nhận chuyên môn.</p>',
        '<p><a href="metrics.json">Metrics JSON</a> · <a href="medical-summary.csv">Medical CSV</a> · <a href="teaching-summary.csv">Teaching CSV</a> · <a href="retrieval.json">Retrieval offline</a> · <a href="../../medresident-benchmark-v1/review-queue.json">Hàng chờ đối chiếu nguồn</a> · <a href="../../medresident-benchmark-v1/split.json">Split và mẫu review chốt trước</a></p>']
    for q in rows(DATA / "questions.jsonl"):
        parts += [f'<article id="{e(q["question_id"])}"><h2>{e(q["question_id"])} · {e(q["topic"])}</h2>',
                  f'<p>{e(q["split"])} · {e(q["task"])}</p><p>{e(q["question"])}</p>',
                  '<details><summary>Rubric và đoạn nguồn đối chiếu</summary><pre>' + e(json.dumps(q["rubric"], ensure_ascii=False, indent=2)) + '</pre>']
        for evidence in q["evidence"]:
            pdf_link = os.path.relpath(ROOT/pdfs[evidence["source_id"]], RUN).replace("\\", "/")
            parts += [f'<h3>{e(evidence["source_id"])} · PDF {evidence["page_start"]}</h3>',
                      f'<a href="{e(pdf_link)}#page={evidence["page_start"]}">Mở PDF gốc tại trang nguồn</a>',
                      '<blockquote>' + e(evidence["content"]) + '</blockquote>']
        parts += ['</details>']
        for sample in (s for s in samples if s["question_id"] == q["question_id"]):
            parts += [f'<details><summary>{e(sample["sample_id"])} · {e(sample["answer_type"])}</summary>',
                      '<h3>Câu trả lời giả lập</h3><p>' + e(sample["payload"]["student_answer"]) + '</p>',
                      '<details><summary>Expected riêng, không gửi model</summary><pre>' + e(json.dumps(references[sample["sample_id"]], ensure_ascii=False, indent=2)) + '</pre></details>']
            for config in ("medical_base", "medical_adapter"):
                path = RUN / config / (sample["sample_id"] + ".json")
                raw = RUN / config / "raw" / path.name
                parts += [f'<h3>{config}</h3>']
                if path.exists():
                    result = read(path)
                    parts += ['<pre>' + e(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre>']
                    if raw.exists():
                        parts += ['<details><summary>Raw không sửa</summary><pre>' + e(read(raw)["text"]) + '</pre></details>']
                    for review in (r for r in reviews if r["config"] == config and r["sample_id"] == sample["sample_id"]):
                        parts += ['<h4>Codex review, chưa có chuyên gia duyệt</h4><pre>' + e(json.dumps(review, ensure_ascii=False, indent=2)) + '</pre>']
                else:
                    parts += ['<p>Chưa có checkpoint; không suy diễn là model đã chạy.</p>']
            parts += ['</details>']
        parts += ['</article>']
    parts += ['<h2>Teaching — fixture kiểm soát</h2>']
    for sample in rows(DATA / "teaching-inputs.jsonl"):
        parts += ['<details><summary>' + e(sample["sample_id"]) + ' · ' + e(sample["context_type"]) + '</summary>',
                  '<pre>' + e(json.dumps(sample["payload"], ensure_ascii=False, indent=2)) + '</pre>']
        for config in ("teaching_base", "teaching_adapter"):
            path = RUN / config / (sample["sample_id"] + ".json")
            if path.exists():
                parts += ['<h3>' + config + '</h3><pre>' + e(json.dumps(read(path), ensure_ascii=False, indent=2)) + '</pre>']
                raw = RUN/config/"raw"/path.name
                if raw.exists():
                    parts += ['<details><summary>Raw Teaching không sửa</summary><pre>' + e(read(raw)["text"]) + '</pre></details>']
                for review in (r for r in reviews if r["config"] == config and r["sample_id"] == sample["sample_id"]):
                    parts += ['<pre>' + e(json.dumps(review, ensure_ascii=False, indent=2)) + '</pre>']
        parts += ['</details>']
    (RUN / "review.html").write_text("\n".join(parts) + '</html>', encoding="utf-8")
    print(json.dumps({"review": str(RUN / "review.html")}))


def packet(config, offset, limit):
    split = read(DATA / "split.json")
    medical = config.startswith("medical")
    selected = split["medical_review_sample_ids" if medical else "teaching_review_sample_ids"]
    inputs = {r["sample_id"]: r for r in rows(DATA / ("medical-inputs.jsonl" if medical else "teaching-inputs.jsonl"))}
    refs = {r["sample_id"]: r for r in rows(DATA / "medical-reference.jsonl")}
    for sid in selected[offset:offset+limit]:
        path = RUN / config / (sid + ".json")
        if not path.exists():
            print(json.dumps({"sample_id": sid, "not_run": True}))
            continue
        source = inputs[sid]
        output = read(path)
        if medical:
            pred = output.get("parsed") or {}
            print(json.dumps({"sample_id": sid, "student": source["payload"]["student_answer"],
                "expected": refs[sid]["expected"], "model": pred,
                "error": output.get("error")}, ensure_ascii=False))
        else:
            print(json.dumps({"sample_id": sid, "question": source["payload"]["question"],
                "student_answer": source["payload"]["student_answer"],
                "medical": source["payload"]["medical_evaluation"],
                "context": source["payload"]["learner_context"], "raw": output.get("parsed"),
                "guarded": output.get("guarded"), "error": output.get("error")}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", choices=["medical_base", "medical_adapter", "teaching_base", "teaching_adapter"])
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.packet:
        packet(args.packet, args.offset, args.limit)
    else:
        render()


if __name__ == "__main__":
    main()
