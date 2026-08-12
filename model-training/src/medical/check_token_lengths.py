import json
from pathlib import Path

from transformers import AutoTokenizer


MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"


def find_repo_root() -> Path:
    current = Path(__file__).resolve()

    for directory in [current.parent, *current.parents]:
        if (
            (directory / ".git").exists()
            and (directory / "model-training").exists()
        ):
            return directory

    raise RuntimeError("Không tìm thấy repository root.")


ROOT = find_repo_root()

DATA_DIR = (
    ROOT
    / "model-training"
    / "prepared-data"
    / "medical"
)

FILES = {
    "train": DATA_DIR / "medical_train_sft.jsonl",
    "validation": DATA_DIR / "medical_validation_sft.jsonl",
}


def read_jsonl(path: Path):
    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def percentile(values, p):
    values = sorted(values)

    if not values:
        return 0

    index = int(round((len(values) - 1) * p))
    return values[index]


def main():
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
    )

    all_lengths = []

    for split, path in FILES.items():
        rows = read_jsonl(path)

        results = []

        for row in rows:
            text = tokenizer.apply_chat_template(
                row["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )

            token_ids = tokenizer(
                text,
                add_special_tokens=False,
            )["input_ids"]

            length = len(token_ids)

            results.append(
                {
                    "sample_id": row["sample_id"],
                    "question_id": row["question_id"],
                    "tokens": length,
                }
            )

            all_lengths.append(length)

        lengths = [
            item["tokens"]
            for item in results
        ]

        longest = max(
            results,
            key=lambda x: x["tokens"],
        )

        print(f"\n=== {split.upper()} ===")
        print("Samples:", len(results))
        print("Min:", min(lengths))
        print("Median:", percentile(lengths, 0.50))
        print("P95:", percentile(lengths, 0.95))
        print("Max:", max(lengths))
        print(
            "Longest sample:",
            longest["sample_id"],
            longest["question_id"],
            longest["tokens"],
        )

        print("\nTop 5 longest:")

        for item in sorted(
            results,
            key=lambda x: x["tokens"],
            reverse=True,
        )[:5]:
            print(
                f"- {item['sample_id']}: "
                f"{item['tokens']} tokens"
            )

    print("\n=== OVERALL ===")
    print("Min:", min(all_lengths))
    print(
        "Median:",
        percentile(all_lengths, 0.50),
    )
    print(
        "P95:",
        percentile(all_lengths, 0.95),
    )
    print("Max:", max(all_lengths))


if __name__ == "__main__":
    main()