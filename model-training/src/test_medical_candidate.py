import json
import os
import time
from typing import Any

# Sử dụng cả hai GPU T4 để chạy MedGemma ở FP32.
os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"

import torch
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
)


MODEL_ID = "google/medgemma-1.5-4b-it"


def get_hf_token() -> str:
    """Đọc Hugging Face token từ môi trường hoặc Kaggle Secrets."""
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


def remove_markdown_fence(text: str) -> str:
    """Loại bỏ ```json ... ``` nếu model tự thêm code fence."""
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    return cleaned


def validate_output(data: dict[str, Any]) -> list[str]:
    """Kiểm tra nhanh cấu trúc output của Medical Model."""
    errors: list[str] = []

    required_fields = [
        "correct_points",
        "incorrect_points",
        "missing_points",
        "evidence",
        "rubric_scores",
        "total_score",
        "max_score",
        "sufficient_evidence",
    ]

    for field in required_fields:
        if field not in data:
            errors.append(f"Thiếu trường: {field}")

    for field in [
        "correct_points",
        "incorrect_points",
        "missing_points",
        "evidence",
        "rubric_scores",
    ]:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} phải là array.")

    if data.get("total_score") != 0:
        errors.append(
            "Bài thử nghiệm này phải có total_score = 0."
        )

    if data.get("max_score") != 4:
        errors.append(
            "Bài thử nghiệm này phải có max_score = 4."
        )

    if data.get("sufficient_evidence") is not True:
        errors.append(
            "sufficient_evidence phải bằng true."
        )

    rubric_scores = data.get("rubric_scores", [])

    if isinstance(rubric_scores, list):
        calculated_total = 0

        for item in rubric_scores:
            if isinstance(item, dict):
                score = item.get("score")

                if isinstance(score, (int, float)):
                    calculated_total += score

        if calculated_total != data.get("total_score"):
            errors.append(
                "Tổng score trong rubric_scores không khớp total_score."
            )

    return errors


def main() -> None:
    if torch.cuda.device_count() < 2:
        raise RuntimeError(
            "Bài kiểm tra FP32 yêu cầu hai GPU."
        )

    hf_token = get_hf_token()

    print("=== MEDICAL MODEL TASK TEST ===")
    print("Model:", MODEL_ID)
    print("Precision: FP32")
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

    # Đây là tình huống giả lập để kiểm tra logic,
    # không phải nội dung y khoa thật.
    prompt = """
Bạn là Medical Model trong hệ thống hỗ trợ học tập cho bác sĩ nội trú.

NHIỆM VỤ:
Đánh giá câu trả lời của người học chỉ dựa trên bằng chứng và rubric
được cung cấp.

QUY TẮC BẮT BUỘC:
1. Không dùng kiến thức bên ngoài.
2. Không tự bổ sung thông tin không có trong bằng chứng.
3. Phân biệt rõ:
   - incorrect_points: điều người học khẳng định sai;
   - missing_points: ý bắt buộc nhưng người học không nêu.
4. Chấm từng tiêu chí đúng theo rubric.
5. Trả về duy nhất một JSON hợp lệ.
6. Không thêm giải thích trước hoặc sau JSON.

BẰNG CHỨNG:
- Phương pháp A được chỉ định khi có điều kiện X.
- Điều kiện Y là chống chỉ định của phương pháp A.

NGUỒN:
- source_id: TEST_SOURCE_001
- page: 10

CÂU HỎI:
Khi nào có thể áp dụng phương pháp A?

CÂU TRẢ LỜI CỦA NGƯỜI HỌC:
Có thể áp dụng phương pháp A khi có điều kiện Y.

RUBRIC:
- Tiêu chí 1: Nêu đúng điều kiện X. Tối đa 2 điểm.
- Tiêu chí 2: Không khẳng định điều kiện Y là chỉ định.
  Tối đa 2 điểm.
- Tổng điểm tối đa: 4.

Trả về đúng cấu trúc:

{
  "correct_points": [],
  "incorrect_points": [],
  "missing_points": [],
  "evidence": [
    {
      "content": "",
      "source_id": "",
      "page": 0
    }
  ],
  "rubric_scores": [
    {
      "criterion": "",
      "score": 0,
      "max_score": 0,
      "reason": ""
    }
  ],
  "total_score": 0,
  "max_score": 4,
  "sufficient_evidence": true
}
""".strip()

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "{",
                }
            ],
        },
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        continue_final_message=True,
    )

    input_device = model.get_input_embeddings().weight.device

    inputs = {
        key: value.to(input_device)
        if torch.is_tensor(value)
        else value
        for key, value in inputs.items()
    }

    input_length = inputs["input_ids"].shape[-1]

    end_of_turn_id = tokenizer.convert_tokens_to_ids(
        "<end_of_turn>"
    )

    eos_token_ids = [tokenizer.eos_token_id]

    if (
        isinstance(end_of_turn_id, int)
        and end_of_turn_id >= 0
        and end_of_turn_id not in eos_token_ids
    ):
        eos_token_ids.append(end_of_turn_id)

    print("\n=== INPUT ===")
    print("Input device:", input_device)
    print("Số token đầu vào:", input_length)
    print("EOS token IDs:", eos_token_ids)

    inference_start = time.perf_counter()

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=500,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=eos_token_ids,
        )

    inference_seconds = time.perf_counter() - inference_start

    generated_ids = output_ids[0, input_length:]

    raw_response = "{" + tokenizer.decode(
        generated_ids,
        skip_special_tokens=False,
    )

    response = "{" + tokenizer.decode(
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

    print("\n=== JSON CHECK ===")

    cleaned_response = remove_markdown_fence(response)

    try:
        parsed = json.loads(cleaned_response)

        print("JSON hợp lệ: True")

        validation_errors = validate_output(parsed)

        if validation_errors:
            print("Kết quả nhiệm vụ: FAILED")

            for index, error in enumerate(
                validation_errors,
                start=1,
            ):
                print(f"{index}. {error}")
        else:
            print("Kết quả nhiệm vụ: PASSED")

        print(
            "Điểm:",
            parsed.get("total_score"),
            "/",
            parsed.get("max_score"),
        )

        print(
            "Số ý sai:",
            len(parsed.get("incorrect_points", [])),
        )

        print(
            "Số ý thiếu:",
            len(parsed.get("missing_points", [])),
        )

    except json.JSONDecodeError as error:
        print("JSON hợp lệ: False")
        print("Kết quả nhiệm vụ: FAILED")
        print("Lỗi JSON:", error)

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