import os
import time

# Chỉ sử dụng GPU đầu tiên trên Kaggle.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
)


MODEL_ID = "google/medgemma-1.5-4b-it"


def get_hf_token() -> str:
    """Đọc Hugging Face token từ biến môi trường hoặc Kaggle Secrets."""
    token = os.environ.get("HF_TOKEN")

    if token:
        return token

    try:
        from kaggle_secrets import UserSecretsClient

        token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception as error:
        raise RuntimeError(
            "Không đọc được HF_TOKEN từ Kaggle Secrets."
        ) from error

    if not token:
        raise RuntimeError("HF_TOKEN đang rỗng.")

    return token


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Không phát hiện GPU CUDA.")

    hf_token = get_hf_token()

    print("=== MEDICAL MODEL CANDIDATE TEST ===")
    print("Model:", MODEL_ID)
    print("GPU:", torch.cuda.get_device_name(0))
    print("HF token available:", bool(hf_token))
    print("Chế độ tải: FP16, không quantization")

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    load_start = time.perf_counter()

    processor = AutoProcessor.from_pretrained(
        MODEL_ID,
        token=hf_token,
        use_fast=False,
    )

    tokenizer = processor.tokenizer

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        token=hf_token,
        dtype=torch.float16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )

    model.eval()

    model.generation_config.pad_token_id = tokenizer.pad_token_id
    model.generation_config.eos_token_id = tokenizer.eos_token_id

    load_seconds = time.perf_counter() - load_start

    # Prompt đơn giản để kiểm tra khả năng sinh văn bản cơ bản.
    prompt = (
        "Answer in English using one short sentence. "
        "What is the purpose of a medical assessment rubric?"
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )

    inputs = inputs.to("cuda:0")
    input_length = inputs["input_ids"].shape[-1]

    print("\n=== INPUT DEBUG ===")
    print("Số token đầu vào:", input_length)
    print("PAD token ID:", tokenizer.pad_token_id)
    print("EOS token ID:", tokenizer.eos_token_id)

    inference_start = time.perf_counter()

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    inference_seconds = time.perf_counter() - inference_start

    generated_ids = output_ids[0, input_length:]

    raw_response = tokenizer.decode(
        generated_ids,
        skip_special_tokens=False,
    )

    response = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
    ).strip()

    peak_vram_gb = (
        torch.cuda.max_memory_allocated()
        / 1024**3
    )

    print("\n=== TOKEN DEBUG ===")
    print("Số token được sinh:", generated_ids.numel())
    print("Token IDs đầu tiên:", generated_ids.tolist()[:20])
    print("Raw output:", repr(raw_response))

    print("\n=== RESPONSE ===")
    print(response if response else "<EMPTY RESPONSE>")

    print("\n=== RUNTIME ===")
    print(f"Thời gian load: {load_seconds:.2f} giây")
    print(f"Thời gian sinh kết quả: {inference_seconds:.2f} giây")
    print(f"Peak VRAM: {peak_vram_gb:.2f} GB")


if __name__ == "__main__":
    main()