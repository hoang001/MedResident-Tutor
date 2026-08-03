import os
import time

# Chỉ sử dụng một GPU.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Không phát hiện GPU CUDA.")

    print("=== TEACHING MODEL CANDIDATE TEST ===")
    print("Model:", MODEL_ID)
    print("GPU:", torch.cuda.get_device_name(0))

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    start_time = time.perf_counter()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quantization_config,
        dtype=torch.float16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )

    model.eval()

    load_seconds = time.perf_counter() - start_time

    # Loại bỏ các tham số sampling không dùng khi do_sample=False.
    model.generation_config.temperature = None
    model.generation_config.top_p = None
    model.generation_config.top_k = None

    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là trợ lý sư phạm cho bác sĩ nội trú. "
                "Chỉ được dựa trên kết quả đánh giá được cung cấp. "
                "Không tự bổ sung kiến thức y khoa."
            ),
        },
        {
            "role": "user",
            "content": (
                "Thông tin chương trình:\n"
                "- Chuyên ngành: Chấn thương chỉnh hình\n"
                "- Học phần: B21CN7 – Chấn thương chỉnh hình chi trên\n"
                "- Round: 2\n"
                "- Năm đào tạo: 2\n\n"
                "Kết quả đánh giá:\n"
                "- Điểm: 4/6\n"
                "- Ý đúng: Nêu được mục tiêu chính\n"
                "- Ý sai: Không có\n"
                "- Ý thiếu: Chưa giải thích đầy đủ cơ chế\n\n"
                "Hãy viết phản hồi ngắn cho người học."
            ),
        },
    ]

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
    )

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
    ).to("cuda:0")

    inference_start = time.perf_counter()

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=180,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    inference_seconds = time.perf_counter() - inference_start

    generated_ids = output_ids[0][inputs["input_ids"].shape[1]:]

    response = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
    ).strip()

    peak_vram_gb = (
        torch.cuda.max_memory_allocated()
        / 1024**3
    )

    print("\n=== RESPONSE ===")
    print(response)

    print("\n=== RUNTIME ===")
    print(f"Thời gian load: {load_seconds:.2f} giây")
    print(f"Thời gian sinh phản hồi: {inference_seconds:.2f} giây")
    print(f"Peak VRAM: {peak_vram_gb:.2f} GB")


if __name__ == "__main__":
    main()