import json
from pathlib import Path


SYSTEM_PROMPT = """Bạn là Medical Evaluation Model trong hệ thống MedResident Tutor.

Nhiệm vụ của bạn là đánh giá câu trả lời của người học chỉ dựa trên:
- câu hỏi;
- evidence được cung cấp;
- rubric được cung cấp.

Quy tắc:
1. Không bổ sung kiến thức y khoa ngoài evidence.
2. correct_points chỉ chứa những ý người học thực sự nêu đúng.
3. incorrect_points chỉ chứa những khẳng định sai thực sự xuất hiện trong câu trả lời.
4. missing_points chứa những tiêu chí cần có nhưng người học chưa nêu hoặc nêu chưa đủ.
5. Chấm điểm riêng từng criterion theo rubric.
6. total_score phải bằng tổng rubric_scores.
7. Nếu evidence không đủ để xác nhận hoặc bác bỏ một nhận định, không tự kết luận nhận định đó là sai và đặt sufficient_evidence=false.
8. Chỉ trả về JSON, không thêm giải thích bên ngoài JSON.
"""


def find_repo_root() -> Path:
    current = Path(__file__).resolve()

    for directory in [current.parent, *current.parents]:
        if (
            (directory / ".git").exists()
            and (directory / "data").exists()
        ):
            return directory

    raise RuntimeError("Không tìm thấy repository root.")


ROOT = find_repo_root()

INPUT_DIR = ROOT / "data" / "training"

OUTPUT_DIR = (
    ROOT
    / "model-training"
    / "prepared-data"
    / "medical"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


SPLITS = {
    "train": "medical_train.jsonl",
    "validation": "medical_validation.jsonl",
    "test": "medical_test.jsonl",
}


def read_jsonl(path: Path):
    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def get_gold(sample):
    for key in (
        "gold_output",
        "medical_evaluation",
        "expected_output",
        "output",
        "assistant",
    ):
        value = sample.get(key)

        if isinstance(value, dict):
            return value

    required = {
        "correct_points",
        "incorrect_points",
        "missing_points",
        "rubric_scores",
        "total_score",
        "max_score",
        "sufficient_evidence",
        "evidence_refs",
    }

    if required.issubset(sample):
        return {
            key: sample[key]
            for key in required
        }

    raise ValueError(
        f"Không tìm thấy gold output: {sample.get('sample_id')}"
    )


def build_user_content(sample):
    payload = {
        "question": sample["question"],
        "student_answer": sample["student_answer"],
        "evidence": sample["evidence"],
        "rubric": sample["rubric"],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def convert_sample(sample):
    gold = get_gold(sample)

    return {
        "sample_id": sample["sample_id"],
        "question_id": sample["question_id"],
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_user_content(sample),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    gold,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
    }


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


def main():
    prepared = {}

    for split, filename in SPLITS.items():
        source_path = INPUT_DIR / filename
        rows = read_jsonl(source_path)

        converted = [
            convert_sample(sample)
            for sample in rows
        ]

        output_path = (
            OUTPUT_DIR
            / f"medical_{split}_sft.jsonl"
        )

        write_jsonl(
            output_path,
            converted,
        )

        prepared[split] = converted

        print(
            f"{split}: "
            f"{len(converted)} samples "
            f"→ {output_path}"
        )

    print("\n=== SAMPLE PREVIEW ===")

    sample = prepared["train"][0]

    print(
        json.dumps(
            sample,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n✅ PREPARE DATASET COMPLETED")


if __name__ == "__main__":
    main()