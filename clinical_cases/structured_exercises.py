"""Manual, source-bound authoring for the existing ten exercises. Never calls a model."""

import argparse
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data/clinical-cases/exercises"

# Binary alternatives negate only a source-supported statement. They do not introduce
# new diagnoses/treatments. These are recognition exercises, not validated clinical exams.
CASE_PARTS = {
    "CASE01": [
        ("Đoạn xương nào được mô tả là bị gãy?", "Đầu dưới xương quay",
         "Không phải đầu dưới xương quay",
         "Đoạn CASE REPORT p005 ghi rõ gãy đầu dưới xương quay trái (left distal radius)."),
        ("Tổn thương gãy có phạm mặt khớp không?", "Có phạm mặt khớp", "Không phạm mặt khớp",
         "Cùng đoạn p005 mô tả tổn thương là intra-articular, tức gãy phạm khớp."),
    ],
    "CASE02": [
        ("Mô tả nào phù hợp với trật khớp trong ca?", "Trật khớp háng phải ra trước",
         "Không phải trật khớp háng phải ra trước",
         "Case presentation p005 ghi anterior dislocation of the right hip trên phim ban đầu."),
        ("Có gãy ổ cối đi kèm không?", "Có gãy ổ cối đi kèm", "Không có gãy ổ cối đi kèm",
         "Cùng đoạn p005 ghi associated acetabular fractures. Không hỏi thêm phân loại CT."),
    ],
    "CASE03": [
        ("Chẩn đoán nào được tác giả xác nhận?", "Hội chứng chèn ép khoang cấp",
         "Không phải hội chứng chèn ép khoang cấp",
         "CASE REPORT p002 nêu phép đo xác nhận ACS (hội chứng chèn ép khoang cấp)."),
        ("Tác giả xác nhận chẩn đoán bằng cách nào?", "Đo áp lực khoang bằng áp kế cầm tay",
         "Không phải đo áp lực khoang bằng áp kế cầm tay",
         "p002 ghi pressure recordings from handheld manometer; số đo 72 và 74 mm Hg."),
    ],
    "CASE04": [
        ("Thận trái lạc chỗ được phát hiện ở đâu?", "Trong tiểu khung",
         "Không nằm trong tiểu khung",
         "CASE REPORT p006 ghi ectopic left kidney within the pelvic cavity."),
        ("Mức độ rách thận được tác giả báo cáo có phải độ III theo AAST?", "Độ III theo AAST",
         "Không phải độ III theo AAST",
         "p006 ghi CT xác nhận grade III laceration theo thang AAST; không suy ra xử trí."),
    ],
    "CASE05": [
        ("Ổ dịch/áp-xe trong ca nằm ở khoang nào?", "Sau phúc mạc", "Không ở sau phúc mạc",
         "CASE PRESENTATION p003 mô tả fluid collection/abscess in the retroperitoneum."),
        ("Tạng thủng được xác nhận khi mổ là gì?", "Tá tràng", "Không phải tá tràng",
         "p004 ghi lỗ thủng 1 cm ở mặt sau phần hai tá tràng; chỉ hỏi tạng đã được xác nhận."),
    ],
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(grading):
    old = grading["exercise_id"]
    qid = old.replace("_V1_", "_V2_")
    short = old.rsplit("_", 1)[1]
    parts = []
    for index, criterion in enumerate(grading["criteria"]):
        p = {
            "id": f"part_{index + 1}", "kind": "single_choice", "max_score": 1,
            "criterion_id": criterion["criterion_id"].replace("_V1_", "_V2_"),
            "evidence_ids": [s.replace("_V1_", "_V2_")
                             for s in criterion["required_source_unit_ids"]],
            "review_focus": [{"label": criterion["description"],
                              "concept_id": (criterion["kg_links"][0]["id"]
                                             if criterion["kg_links"] else None)}],
        }
        if short.startswith("XR") and index == 1:
            ref = grading["evidence"][0]["source_ref"]
            box = ref["bbox_original"]
            asset = grading["assets"][0]
            # Original VOC coordinates and unmodified displayed pixels use identity geometry.
            row = min(3, int(((box["ymin"] + box["ymax"]) / 2) / asset["height"] * 3) + 1)
            col = min(3, int(((box["xmin"] + box["xmax"]) / 2) / asset["width"] * 3) + 1)
            assert ref["derived_grid"] == {"row": row, "column": col}
            correct_id = f"r{row}c{col}"
            p.update(
                kind="grid_location", asset_id=asset["asset_id"],
                label="Tâm vùng gãy trên ảnh số 1 nằm trong ô nào của lưới 3×3?",
                options=[{"id": f"r{r}c{c}", "label": f"Hàng {r}, cột {c}"}
                         for r in range(1, 4) for c in range(1, 4)],
                correct_option_id=correct_id,
                explanation=(f"Tâm box nguồn ở hàng {row}, cột {col}. Hàng tính từ trên xuống, "
                             "cột từ trái sang, bắt đầu từ 1 trên ảnh gốc không xoay/lật. "
                             "Đây là phép tính hình học từ annotation, không phải phân loại giải phẫu."),
                correct_feedback="Ô bạn chọn trùng vị trí tâm box annotation của ảnh số 1.",
                incorrect_feedback={f"r{r}c{c}":
                    f"Bạn chọn hàng {r}, cột {c}; tâm box nguồn ở hàng {row}, cột {col}."
                    for r in range(1, 4) for c in range(1, 4) if (r, c) != (row, col)},
                unanswered_feedback="Bạn chưa chọn ô. Đối chiếu vị trí tâm box trong ảnh lời giải.",
            )
        else:
            if short.startswith("XR"):
                label, right, wrong, explanation = (
                    "Ảnh số 1 có vùng gãy được annotation nguồn đánh dấu không?",
                    "Có vùng gãy", "Không có vùng gãy",
                    "Pascal VOC nguồn gán nhãn fracture cho box trên ảnh số 1. "
                    "Annotation không cung cấp đáp án điều trị hoặc đánh giá mức độ.",
                )
            else:
                label, right, wrong, explanation = CASE_PARTS[short][index]
            # IDs are opaque and independent of display labels; fixed per authored revision.
            right_id, wrong_id = ("o2", "o1") if index == 1 else ("o1", "o2")
            p.update(
                label=label, correct_option_id=right_id,
                options=sorted([{"id": right_id, "label": right},
                                {"id": wrong_id, "label": wrong}], key=lambda o: o["id"]),
                explanation=explanation,
                correct_feedback=f"Lựa chọn “{right}” khớp mô tả trong nguồn của bài.",
                incorrect_feedback={wrong_id: f"Bạn chọn “{wrong}”; nguồn của bài ghi “{right}”."},
                unanswered_feedback=f"Bạn chưa trả lời phần này. Đáp án đối chiếu: {right}.",
            )
        parts.append(p)
    parts.append({"id": "explanation", "kind": "short_explanation", "max_score": 0,
                  "label": "Giải thích ngắn (không bắt buộc, chưa tính điểm)", "max_length": 4000})
    return {
        "schema_version": "structured-v1", "revision_id": qid, "legacy_question_id": old,
        "review_status": "source_checked_expert_review_pending",
        "scoring_policy": "independent_exact_id_fixed_denominator", "parts": parts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", action="store_true", help="Also author eight staging records")
    args = parser.parse_args()
    folder = OUT / "structured"
    folder.mkdir(exist_ok=True)
    records = []
    for row in read(OUT / "manifest.json")["rows"]:
        if not row["demo"] and not args.staging:
            continue
        grading = read(OUT / row["grading_path"])
        exercise = build(grading)
        target = folder / (exercise["revision_id"] + ".json")
        target.write_text(json.dumps(exercise, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append({"question_id": exercise["revision_id"],
                        "legacy_question_id": exercise["legacy_question_id"],
                        "status": "demo" if row["demo"] else "staging_not_imported",
                        "definition_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "missing_source_criteria": [], "expert_verified": False})
    (folder / "manifest.json").write_text(
        json.dumps({"rows": records, "model_calls": 0}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"authored": len(records), "model_calls": 0}))


if __name__ == "__main__":
    main()
