import json
from pathlib import Path

if __package__:
    from .inference import SYSTEM_PROMPT, build_user_content
else:
    from inference import SYSTEM_PROMPT, build_user_content




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