import json
import os
import time

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
    BitsAndBytesConfig,
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
    if not torch.cuda.is_available():
        raise RuntimeError("Không phát hiện GPU CUDA.")

    hf_token = get_hf_token()

    print("=== MEDICAL MODEL CANDIDATE TEST ===")
    print("Model:", MODEL_ID)
    print("GPU:", torch.cuda.get_device_name(0))
    print("HF token available:", bool(hf_token))

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    load_start = time.perf_counter()

    processor = AutoProcessor.from_pretrained(
        MODEL_ID,
        token=hf_token,
    )

    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        token=hf_token,
        quantization_config=quantization_config,
        device_map={"": 0},
        dtype=torch.float16,
        low_cpu_mem_usage=True,
    )

    model.eval()

    load_seconds = time.perf_counter() - load_start

    prompt = (
    "Answer in English using one short sentence: "
    "What is the purpose of a medical assessment rubric?"
).strip()

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
    ).to("cuda:0")

    input_length = inputs["input_ids"].shape[-1]

    inference_start = time.perf_counter()

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=400,
            do_sample=False,
        )

    inference_seconds = time.perf_counter() - inference_start

    generated_ids = output_ids[0][input_length:]
    print("\n=== TOKEN DEBUG ===")
    print("Số token được sinh:", generated_ids.numel())
    print("Token IDs đầu tiên:", generated_ids.tolist()[:20])
    print(
        "Raw output:",
        repr(
            processor.decode(
                generated_ids,
                skip_special_tokens=False,
            )
        ),
    )

    response = processor.decode(
        generated_ids,
        skip_special_tokens=True,
    ).strip()

    peak_vram_gb = torch.cuda.max_memory_allocated() / 1024**3

    print("\n=== RESPONSE ===")
    print(response)

    print("\n=== JSON CHECK ===")

    cleaned_response = response

    if cleaned_response.startswith("```json"):
        cleaned_response = cleaned_response[7:]

    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response[3:]

    if cleaned_response.endswith("```"):
        cleaned_response = cleaned_response[:-3]

    try:
        parsed = json.loads(cleaned_response.strip())
        print("JSON hợp lệ: True")
        print(
            "Tổng điểm:",
            parsed.get("total_score"),
            "/",
            parsed.get("max_score"),
        )
    except json.JSONDecodeError as error:
        print("JSON hợp lệ: False")
        print("Lỗi:", error)

    print("\n=== RUNTIME ===")
    print(f"Thời gian load: {load_seconds:.2f} giây")
    print(f"Thời gian sinh kết quả: {inference_seconds:.2f} giây")
    print(f"Peak VRAM: {peak_vram_gb:.2f} GB")


if __name__ == "__main__":
    main()