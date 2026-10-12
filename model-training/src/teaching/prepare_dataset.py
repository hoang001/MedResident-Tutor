"""Prepare chat SFT files without modifying source data or gold output."""

import json

if __package__:
    from .validate_dataset import ROOT, validate
else:
    from validate_dataset import ROOT, validate

OUTPUT_DIR = ROOT / "model-training" / "prepared-data" / "teaching"
SYSTEM_PROMPT = """Bạn là Teaching Model trong MedResident Tutor.
Medical Evaluation là nguồn sự thật chuyên môn duy nhất.
Không đánh giá lại đúng/sai. Không thay đổi score hoặc xuất bất kỳ field điểm nào.
Không bổ sung factual medical knowledge ngoài Medical Evaluation; question và
student_answer chỉ cung cấp bối cảnh, không phải nguồn sự thật chuyên môn.
learner_context chỉ ảnh hưởng cách dạy, learning priority và thứ tự ôn,
không thay đổi Medical Evaluation. Phản ánh lỗi lặp lại, cải thiện gần đây,
mastery và lịch sử khi chúng tồn tại; không bịa lịch sử khi context rỗng.
Khi sufficient_evidence=false, phải thận trọng và nêu rõ chưa đủ căn cứ.
strengths ánh xạ từng correct_point; corrections ánh xạ đúng 1:1 incorrect_points;
missing_focus ánh xạ đúng 1:1 missing_points. Không tự thêm hoặc bỏ các ý này.
Chỉ xuất JSON đúng Teaching schema v1, không markdown, không văn bản bên ngoài:
{
  "strengths": [],
  "corrections": [],
  "missing_focus": [],
  "learning_priority": [],
  "feedback_text": "",
  "follow_up_question": null
}
strengths: list chuỗi. corrections: list object {"incorrect_point": "", "feedback": ""}.
missing_focus: list object {"missing_point": "", "feedback": ""}.
learning_priority: list object {"focus": "", "priority": "high|medium|low", "reason": ""}.
feedback_text là chuỗi không rỗng; follow_up_question là chuỗi hoặc null.
Không thêm field. Viết phản hồi bằng tiếng Việt, chỉ dựa trên các factual anchor
trong Medical Evaluation; learner_context chỉ dùng để cá nhân hóa sư phạm.
"""


def convert_sample(row):
    inp = row["input"]
    payload = {key: inp[key] for key in (
        "question", "student_answer", "medical_evaluation", "learner_context", "metadata"
    )}
    return {"sample_id": row["sample_id"], "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        {"role": "assistant", "content": json.dumps(row["gold_output"], ensure_ascii=False)},
    ]}


def main():
    rows, errors, _ = validate()
    if errors:
        raise ValueError(f"Dataset validation failed ({len(errors)} errors); nothing written")
    converted = {split: [convert_sample(row) for row in samples] for split, samples in rows.items()}
    for split, samples in rows.items():
        for raw, prepared in zip(samples, converted[split]):
            if json.loads(prepared["messages"][2]["content"]) != raw["gold_output"]:
                raise ValueError("Gold round-trip mismatch")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for split, samples in converted.items():
        path = OUTPUT_DIR / f"teaching_{split}_sft.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in samples), encoding="utf-8")
        print(f"{split}: {len(samples)} samples -> {path}")


if __name__ == "__main__":
    main()
