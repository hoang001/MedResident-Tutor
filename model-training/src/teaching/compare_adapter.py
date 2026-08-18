import json
import os
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "sample_data" / "teaching_train.jsonl"
ADAPTER_DIR = ROOT / "outputs" / "teaching-smoke" / "adapter"


def generate_response(model, tokenizer, input_ids) -> str:
    with torch.no_grad():
        output_ids = model.generate(
            input_ids=input_ids,
            max_new_tokens=150,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = output_ids[0][input_ids.shape[1]:]

    return tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
    ).strip()


def load_test_messages() -> list[dict]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        sample = json.loads(file.readline())

    # Chỉ lấy system và user, không đưa đáp án mẫu cho model.
    return sample["messages"][:2]


def main() -> None:
    if not ADAPTER_DIR.exists():
        raise FileNotFoundError(
            f"Không tìm thấy LoRA adapter tại: {ADAPTER_DIR}"
        )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    messages = load_test_messages()

    prompt_text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    input_ids = tokenizer(
        prompt_text,
        return_tensors="pt",
    ).input_ids.to("cuda:0")

    print("=== BASE MODEL ===")

    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float16,
    ).to("cuda:0")

    base_model.eval()

    base_response = generate_response(
        base_model,
        tokenizer,
        input_ids,
    )

    print(base_response)

    del base_model
    torch.cuda.empty_cache()

    print("\n=== MODEL GẮN LORA ADAPTER ===")

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float16,
    ).to("cuda:0")

    model = PeftModel.from_pretrained(
        model,
        ADAPTER_DIR,
    )

    model.eval()

    adapter_response = generate_response(
        model,
        tokenizer,
        input_ids,
    )

    print(adapter_response)


if __name__ == "__main__":
    main()