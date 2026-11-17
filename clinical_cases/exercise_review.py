"""Review authored staging separately from learner API payloads."""
import html
import json

from .exercises import OUT
from .io import DATA, read, sha, write
from .pmc import blocks_and_figures


def verify():
    manifest = read(OUT / "manifest.json")
    checked, assets = 0, []
    for row in manifest["rows"]:
        learner, grading = read(OUT / row["learner_path"]), read(OUT / row["grading_path"])
        if any(key in learner for key in ("criteria", "evidence", "reference_answer", "source", "annotations")):
            raise ValueError("learner_contains_grading_payload")
        if sum(c["max_score"] for c in grading["criteria"]) != grading["max_score"]:
            raise ValueError("rubric_sum_mismatch")
        for asset in grading["assets"]:
            if sha((OUT / asset["bundle_path"]).read_bytes()) != asset["sha256"] or asset["transformation"]["pixel_edits"]:
                raise ValueError("learner_asset_modified")
            if asset["source_image_id"] in asset["bundle_path"]:
                raise ValueError("answer_bearing_source_filename_exposed")
            assets.append(asset)
        if sha((OUT / grading["packet"]["path"]).read_bytes()) != grading["packet"]["sha256"]:
            raise ValueError("packet_changed")
        for evidence in grading["evidence"]:
            ref = evidence["source_ref"]
            if "block_id" in ref:
                pmcid = evidence["source_id"].removeprefix("SRC_CASE_")
                parsed = blocks_and_figures((DATA / "raw/pmc" / (pmcid + ".xml")).read_bytes())
                block = next(b for b in parsed["blocks"] if b["block_id"] == ref["block_id"])
                if block["text"][ref["normalized_char_start"]:ref["normalized_char_end"]] != evidence["content_en"]:
                    raise ValueError("exercise_evidence_not_source_excerpt")
            else:
                if sha((DATA / ref["annotation_path"]).read_bytes()) != ref["annotation_sha256"]:
                    raise ValueError("annotation_source_changed")
        checked += 1
    report = {"authored_exercises": checked, "source_checked_not_expert_verified": checked,
              "learner_assets": len(assets), "demo_ids": manifest["demo_ids"],
              "pixel_modifications": 0, "expert_verified": False, "llm_calls": 0}
    write(OUT / "validation.json", report)
    return report


def render():
    report = verify()
    def e(value):
        return html.escape(str(value), quote=True)
    parts = ['<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Review bài tập biên soạn</title>',
             '<style>body{font:17px/1.6 Arial,sans-serif;background:#f7faf9;color:#18312d;margin:auto;padding:24px;max-width:1080px}a{color:#116c60}a:focus-visible,summary:focus-visible{outline:3px solid #116c60}article{border-top:1px solid #cbdad7;padding:24px 0}p{max-width:75ch;white-space:pre-wrap}summary{cursor:pointer;padding:12px 0;font-weight:bold}.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px}.canvas{position:relative}.canvas img{display:block;width:100%;height:auto}.canvas svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}figure{margin:0}small{display:block}h1{font-size:2rem}details{margin:16px 0}.notice{padding:16px;background:#e8f4f1}@media(max-width:600px){body{padding:16px}.images{grid-template-columns:1fr}}</style>',
             '<h1>Review 10 bài tập biên soạn từ nguồn</h1><p>5 ca bệnh và 5 lượt chụp. Không phải câu hỏi trích nguyên văn. Kiểm tra nguồn không thay chuyên gia duyệt. Bản này chứa đáp án, chỉ phục vụ review nội bộ.</p>',
             '<p class="notice">Hai demo V2 chấm xác định theo ID lựa chọn và rubric biên soạn; không gọi model, không cập nhật mastery. Bản V1 tự luận vẫn giữ chế độ riêng. Tám bài V2 còn lại chỉ ở staging, chưa import. Kiểm nguồn không thay chuyên gia duyệt. Ảnh gốc giữ nguyên byte; khung chú giải là SVG riêng sau nộp.</p>']
    for item in read(OUT / "manifest.json")["rows"]:
        learner, g = read(OUT / item["learner_path"]), read(OUT / item["grading_path"])
        parts += [f'<article id="{e(item["exercise_id"])}"><h2>{e(learner["title"])}{" — demo" if item["demo"] else " — staging"}</h2>',
                  f'<p>{e(g["selection_reason"])}</p><h3>Đề học viên</h3><p>{e(learner["presentation"])}</p><div class="images">']
        for i, a in enumerate(g["assets"], 1):
            parts.append(f'<figure><a href="{e(a["bundle_path"])}"><img src="{e(a["bundle_path"])}" alt="Ảnh {i} của bài tập" loading="lazy" style="width:100%;height:auto"></a><figcaption>Ảnh {i}</figcaption></figure>')
        parts += ['</div>', f'<p>{e(learner["question"])}</p><p>{e(learner["notice"])}</p>',
                  '<details><summary>Bản gốc tiếng Anh và căn cứ dịch</summary><pre>' + e(json.dumps(read(OUT / "translations" / (item["exercise_id"] + ".json")), ensure_ascii=False, indent=2)) + '</pre></details>',
                  '<details><summary>Đáp án, rubric và căn cứ từng tiêu chí</summary><ol>']
        structured_path = OUT / "structured" / (item["exercise_id"].replace("_V1_", "_V2_") + ".json")
        if structured_path.exists():
            s = read(structured_path)
            parts += ['<li><h3>Bản structured: đề → lựa chọn → đáp án → điểm → nhận xét → nguồn</h3>',
                      f'<p>{e(s["revision_id"])} · {"Demo đã import" if item["demo"] else "Staging, không import"}</p>',
                      '<p>Mỗi phần độc lập, đúng toàn bộ ID được 1 điểm, sai hoặc bỏ trống 0 điểm. '
                      'Phân biệt sai và chưa trả lời; mẫu số cố định 2. Không có nhánh điều kiện. '
                      'Giải thích tự do giữ nguyên, không tính điểm. Các lựa chọn phủ định chỉ đối chiếu '
                      'mệnh đề trong nguồn, không tự thêm chẩn đoán hoặc distractor y khoa mới.</p>']
            for p in s["parts"]:
                parts += [f'<h4>{e(p["label"])}</h4><p>ID: {e(p["id"])} · {e(p["kind"])} · {p["max_score"]} điểm</p>']
                if not p["max_score"]:
                    parts += ['<p>Tự chọn, chưa tính điểm, tối đa 4000 ký tự.</p>']
                    continue
                parts += ['<ul>']
                for o in p["options"]:
                    right = o["id"] == p["correct_option_id"]
                    feedback = p["correct_feedback"] if right else p["incorrect_feedback"][o["id"]]
                    parts += [f'<li>{e(o["id"])} · {e(o["label"])} → '
                              f'{p["max_score"] if right else 0} điểm · {"Đúng" if right else "Sai"}'
                              f'<p>{e(feedback)}</p></li>']
                parts += ['</ul>', '<p>Bỏ trống → 0 điểm · Chưa trả lời: ' + e(p["unanswered_feedback"]) + '</p>',
                          '<p>Giải thích: ' + e(p["explanation"]) + '</p>',
                          '<p>Nên ôn: ' + e('; '.join(f["label"] for f in p["review_focus"])) + '</p>']
                for ev in g["evidence"]:
                    if ev["source_unit_id"].replace("_V1_", "_V2_") in p["evidence_ids"]:
                        parts += ['<blockquote>' + e(ev["content_en"]) + '</blockquote>',
                                  '<pre>' + e(json.dumps(ev["source_ref"], ensure_ascii=False, indent=2)) + '</pre>']
            parts += ['</li>']
        for criterion in g["criteria"]:
            refs = [ev for ev in g["evidence"] if ev["source_unit_id"] in criterion["required_source_unit_ids"]]
            parts += [f'<li>{e(criterion["reference_answer_vi"])} — {criterion["max_score"]} điểm tối đa.<p>Tương đương: {e(", ".join(criterion["acceptable_variants"]))}</p>',
                      *['<blockquote>' + e(ev["content_en"]) + '</blockquote><pre>' + e(json.dumps(ev["source_ref"], ensure_ascii=False, indent=2)) + '</pre>' for ev in refs], '</li>']
        parts += ['</ol><div class="images">']
        for a in g["assets"]:
            annotations = [ann for ann in g["answer_annotations"] if ann["asset_id"] == a["asset_id"]]
            if annotations:
                rects = ''.join(f'<rect x="{ann["box"]["xmin"]}" y="{ann["box"]["ymin"]}" width="{ann["box"]["xmax"]-ann["box"]["xmin"]}" height="{ann["box"]["ymax"]-ann["box"]["ymin"]}" fill="none" stroke="#ffcd38" stroke-width="4"/>' for ann in annotations)
                parts.append(f'<figure><div class="canvas"><img src="{e(a["bundle_path"])}" alt="Ảnh đối chiếu sau nộp"><svg viewBox="0 0 {a["width"]} {a["height"]}">{rects}</svg></div><figcaption>Chú giải nguồn trên hình học gốc</figcaption></figure>')
        source = g["source"]
        parts += ['</div><p>' + e(source["attribution_text"]) + '</p>', f'<a href="{e(source["original_url"])}">Nguồn</a> · <a href="{e(source["license_url"])}">{e(source["license"])}</a>',
                  '<pre>' + e(json.dumps({"kg_links": [c["kg_links"] for c in g["criteria"]], "source_variant_note": g.get("source_variant_note"), "expert_verified": False}, ensure_ascii=False, indent=2)) + '</pre></details></article>']
    parts += ['<h2>Các mục cần duyệt thêm</h2><p>Kiểm tra chuyên môn và bản dịch; mức độ phù hợp với bác sĩ nội trú; quyền riêng tư ở độ phân giải gốc; độ chính xác annotation. Chưa có xác nhận đạt năng lực thực hành. Năm bài X-quang chỉ hỏi nhãn và vị trí tương đối, không hỏi điều trị/phân loại.</p></html>']
    (OUT / "review.html").write_text("\n".join(parts), encoding="utf-8")
    (OUT / "review.md").write_text("# Review bài tập\n\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n\nMở review.html để xem đề → lựa chọn → đáp án → điểm → nhận xét → nguồn. Hai demo V2 chấm xác định, không model. Tám bài V2 còn lại ở staging, chưa import. V1 tự luận còn nguyên. Chưa có chuyên gia duyệt.\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    render()
