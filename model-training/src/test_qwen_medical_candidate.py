import json
import os
import time
from typing import Any

# Chỉ sử dụng một GPU T4.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"


def contains_keyword(items: list[Any], keyword: str) -> bool:
    """Kiểm tra danh sách có chứa từ khóa mong đợi hay không."""
    normalized_keyword = keyword.casefold()

    return any(
        isinstance(item, str)
        and normalized_keyword in item.casefold()
        for item in items
    )


def parse_first_json(text: str) -> dict[str, Any]:
    """
    Đọc object JSON đầu tiên trong output.

    Hàm vẫn hoạt động nếu model thêm code fence hoặc nội dung thừa
    sau dấu đóng JSON.
    """
    start_index = text.find("{")

    if start_index == -1:
        raise json.JSONDecodeError(
            "Không tìm thấy ký tự mở JSON.",
            text,
            0,
        )

    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(text[start_index:])

    if not isinstance(parsed, dict):
        raise ValueError("Output JSON phải là một object.")

    return parsed


def validate_output(data: dict[str, Any]) -> list[str]:
    """Kiểm tra cấu trúc và ngữ nghĩa của bài thử nghiệm X/Y."""
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

    list_fields = [
        "correct_points",
        "incorrect_points",
        "missing_points",
        "evidence",
        "rubric_scores",
    ]

    for field in list_fields:
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

    correct_points = data.get("correct_points", [])
    incorrect_points = data.get("incorrect_points", [])
    missing_points = data.get("missing_points", [])
    rubric_scores = data.get("rubric_scores", [])
    evidence = data.get("evidence", [])

    if isinstance(correct_points, list) and correct_points:
        errors.append(
            "Tình huống này không được có correct_points."
        )

    if (
        isinstance(incorrect_points, list)
        and not contains_keyword(incorrect_points, "Y")
    ):
        errors.append(
            "incorrect_points phải chỉ ra rằng người học "
            "đã khẳng định sai điều kiện Y."
        )

    if (
        isinstance(missing_points, list)
        and not contains_keyword(missing_points, "X")
    ):
        errors.append(
            "missing_points phải chỉ ra rằng người học "
            "không nêu điều kiện X."
        )

    if isinstance(rubric_scores, list):
        if len(rubric_scores) != 2:
            errors.append(
                "Tình huống này phải có đúng 2 rubric_scores."
            )

        calculated_total = 0.0

        for item in rubric_scores:
            if not isinstance(item, dict):
                errors.append(
                    "Mỗi phần tử rubric_scores phải là object."
                )
                continue

            score = item.get("score")
            max_score = item.get("max_score")

            if not isinstance(score, (int, float)):
                errors.append(
                    "score trong rubric_scores phải là số."
                )
                continue

            if not isinstance(max_score, (int, float)):
                errors.append(
                    "max_score trong rubric_scores phải là số."
                )
                continue

            if score < 0 or score > max_score:
                errors.append(
                    f"Điểm rubric không hợp lệ: "
                    f"{score}/{max_score}."
                )

            calculated_total += score

        if calculated_total != data.get("total_score"):
            errors.append(
                "Tổng score trong rubric_scores "
                "không khớp total_score."
            )

        if isinstance(evidence, list):
            if not evidence:
                errors.append(
                    "Output phải có ít nhất một evidence."
                )

            for index, item in enumerate(evidence, start=1):
                if not isinstance(item, dict):
                    errors.append(
                        f"Evidence {index} phải là object."
                    )
                    continue

                if item.get("source_id") != "TEST_SOURCE_001":
                    errors.append(
                        f"Evidence {index} phải giữ đúng source_id."
                    )

                if item.get("page") != 10:
                    errors.append(
                        f"Evidence {index} phải giữ đúng page = 10."
                    )

    return errors


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Không phát hiện GPU CUDA.")

    print("=== QWEN MEDICAL MODEL TASK TEST ===")
    print("Model:", MODEL_ID)
    print("GPU:", torch.cuda.get_device_name(0))
    print("Chế độ tải: 4-bit NF4")

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    load_start = time.perf_counter()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quantization_config,
        dtype=torch.float16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )

    model.eval()

    # Tắt các cấu hình sampling mặc định vì bài test cần deterministic.
    model.generation_config.do_sample = False
    model.generation_config.temperature = None
    model.generation_config.top_p = None
    model.generation_config.top_k = None

    load_seconds = time.perf_counter() - load_start

    system_prompt = (
        "Bạn là Medical Model trong hệ thống hỗ trợ học tập "
        "cho bác sĩ nội trú. Bạn chỉ được đánh giá dựa trên "
        "bằng chứng và rubric được cung cấp."
    )

    prompt = """
NHIỆM VỤ:
Đánh giá câu trả lời của người học chỉ dựa trên bằng chứng và rubric
được cung cấp.

QUY TẮC BẮT BUỘC:
1. Không sử dụng kiến thức bên ngoài.
2. Không tự bổ sung thông tin không có trong bằng chứng.
3. correct_points chỉ chứa ý người học đã nêu đúng.
4. incorrect_points chứa điều người học đã khẳng định sai.
5. missing_points chứa mọi ý bắt buộc trong rubric nhưng người học
   không nêu, kể cả khi ý đó đã được nhắc trong reason của rubric.
6. Chấm từng tiêu chí đúng theo rubric.
7. Trả về duy nhất một JSON hợp lệ.
8. Không thêm Markdown hoặc giải thích ngoài JSON.
9. sufficient_evidence = true khi bằng chứng được cung cấp đủ để
   chấm toàn bộ các tiêu chí trong rubric, dù câu trả lời của người
   học đúng, sai hay còn thiếu.

10. sufficient_evidence chỉ bằng false khi bằng chứng nguồn không đủ
    để đánh giá ít nhất một tiêu chí trong rubric.
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

Cấu trúc JSON bắt buộc:

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

    # Prefill dấu mở JSON để model tiếp tục thẳng phần output.
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": prompt,
        },
        {
            "role": "assistant",
            "content": "{",
        },
    ]

    inputs = tokenizer.apply_chat_template(
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

    eos_token_ids = model.generation_config.eos_token_id

    if eos_token_ids is None:
        eos_token_ids = tokenizer.eos_token_id

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

    # Dấu { nằm trong prefill nên phải ghép lại khi đọc output mới sinh.
    response = "{" + tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
    ).strip()

    print("\n=== RESPONSE ===")
    print(response if response else "<EMPTY RESPONSE>")

    print("\n=== JSON CHECK ===")

    try:
        parsed = parse_first_json(response)

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
            "Số ý đúng:",
            len(parsed.get("correct_points", [])),
        )
        print(
            "Số ý sai:",
            len(parsed.get("incorrect_points", [])),
        )
        print(
            "Số ý thiếu:",
            len(parsed.get("missing_points", [])),
        )

    except (json.JSONDecodeError, ValueError) as error:
        print("JSON hợp lệ: False")
        print("Kết quả nhiệm vụ: FAILED")
        print("Lỗi JSON:", error)

    peak_vram_gb = (
        torch.cuda.max_memory_allocated()
        / 1024**3
    )

    print("\n=== RUNTIME ===")
    print(f"Thời gian load: {load_seconds:.2f} giây")
    print(
        f"Thời gian sinh kết quả: "
        f"{inference_seconds:.2f} giây"
    )
    print(f"Peak VRAM: {peak_vram_gb:.2f} GB")


if __name__ == "__main__":
    main()