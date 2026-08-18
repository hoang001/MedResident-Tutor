import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "sample_data" / "medical_output.json"


def main() -> None:
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        medical_result = json.load(file)

    prompt = f"""
Bạn là trợ lý sư phạm cho bác sĩ nội trú.

Hãy viết nhận xét dễ hiểu dựa hoàn toàn vào kết quả đánh giá sau:

Câu hỏi: {medical_result["question"]}
Câu trả lời người học: {medical_result["student_answer"]}
Điểm: {medical_result["total_score"]}/{medical_result["max_score"]}

Ý đúng:
{"\n".join(f"- {item}" for item in medical_result["correct_points"]) or "- Không có"}

Ý sai:
{"\n".join(f"- {item}" for item in medical_result["incorrect_points"]) or "- Không có"}

Ý còn thiếu:
{"\n".join(f"- {item}" for item in medical_result["missing_points"]) or "- Không có"}

Không được tự bổ sung kiến thức y khoa ngoài dữ liệu trên.
""".strip()

    print(prompt)


if __name__ == "__main__":
    main()