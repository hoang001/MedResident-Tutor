import os
import time

# Cho phép chương trình sử dụng cả hai GPU T4.
os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"

import torch
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
)


MODEL_ID = "google/medgemma-1.5-4b-it"


def get_hf_token() -> str:
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
    if torch.cuda.device_count() < 2:
        raise RuntimeError(
            "Bài kiểm tra FP32 này yêu cầu hai GPU."
        )

    hf_token = get_hf_token()

    print("=== MEDICAL MODEL FP32 TEST ===")
    print("Model:", MODEL_ID)
    print("Số GPU:", torch.cuda.device_count())

    for index in range(torch.cuda.device_count()):
        print(
            f"GPU {index}:",
            torch.cuda.get_device_name(index),
        )
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(index)

    load_start = time.perf_counter()

    processor = AutoProcessor.from_pretrained(
        MODEL_ID,
        token=hf_token,
        use_fast=False,
    )

    tokenizer = processor.tokenizer

    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        token=hf_token,
        dtype=torch.float32,
        device_map="balanced",
        max_memory={
            0: "13GiB",
            1: "13GiB",
        },
        low_cpu_mem_usage=True,
    )

    model.eval()

    load_seconds = time.perf_counter() - load_start

    print("\n=== DEVICE MAP ===")
    print(model.hf_device_map)

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

    # Đặt input tại GPU chứa lớp embedding đầu vào.
    input_device = model.get_input_embeddings().weight.device

    inputs = {
        key: value.to(input_device)
        if torch.is_tensor(value)
        else value
        for key, value in inputs.items()
    }

    input_length = inputs["input_ids"].shape[-1]

    print("\n=== INPUT DEBUG ===")
    print("Input device:", input_device)
    print("Số token đầu vào:", input_length)
    print("PAD token ID:", tokenizer.pad_token_id)
    print("EOS token ID:", tokenizer.eos_token_id)

    # Kiểm tra trực tiếp logits trước khi generate.
    with torch.inference_mode():
        outputs = model(
            **inputs,
            use_cache=False,
        )

    last_logits = outputs.logits[:, -1, :]

    print("\n=== LOGITS DEBUG ===")
    print(
        "Tất cả logits hữu hạn:",
        torch.isfinite(last_logits).all().item(),
    )
    print(
        "Số NaN:",
        torch.isnan(last_logits).sum().item(),
    )
    print(
        "Số Inf:",
        torch.isinf(last_logits).sum().item(),
    )
    print(
        "Token argmax:",
        torch.argmax(last_logits, dim=-1).item(),
    )

    del outputs
    del last_logits

    inference_start = time.perf_counter()

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=80,
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

    print("\n=== TOKEN DEBUG ===")
    print("Số token được sinh:", generated_ids.numel())
    print(
        "Token IDs đầu tiên:",
        generated_ids.tolist()[:20],
    )
    print("Raw output:", repr(raw_response))

    print("\n=== RESPONSE ===")
    print(response if response else "<EMPTY RESPONSE>")

    print("\n=== RUNTIME ===")
    print(f"Thời gian load: {load_seconds:.2f} giây")
    print(
        f"Thời gian sinh kết quả: "
        f"{inference_seconds:.2f} giây"
    )

    for index in range(torch.cuda.device_count()):
        peak_vram = (
            torch.cuda.max_memory_allocated(index)
            / 1024**3
        )

        print(
            f"Peak VRAM GPU {index}: "
            f"{peak_vram:.2f} GB"
        )


if __name__ == "__main__":
    main()