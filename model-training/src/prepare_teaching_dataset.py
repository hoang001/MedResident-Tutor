import json
from pathlib import Path

from transformers import AutoTokenizer

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "sample_data" / "teaching_train.jsonl"


def main() -> None:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    with DATA_FILE.open("r", encoding="utf-8") as file:
        samples = [json.loads(line) for line in file if line.strip()]

    for sample in samples:
        text = tokenizer.apply_chat_template(
            sample["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )

        print("=== DỮ LIỆU SAU KHI FORMAT ===")
        print(text)


if __name__ == "__main__":
    main()