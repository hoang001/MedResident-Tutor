"""Side-effect-free Medical pilot primitives shared with inference serving.

GPU imports occur only inside load_model. Importing this file opens no datasets,
creates no directories and downloads no artifacts.
"""

import json
import re

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MAX_NEW_TOKENS = 1200

SYSTEM_PROMPT = """Bạn là Medical Evaluation Model trong hệ thống MedResident Tutor.

Nhiệm vụ: đánh giá câu trả lời của người học CHỈ dựa trên question, student_answer, evidence và rubric được cung cấp.

QUY TẮC:
1. Không bổ sung kiến thức y khoa ngoài evidence.
2. Chỉ đưa vào correct_points những ý thực sự xuất hiện trong student_answer và được evidence hỗ trợ.
3. Không được sao chép một criterion vào correct_points chỉ vì criterion đó có trong rubric.
4. incorrect_points chỉ chứa claim sai thực sự xuất hiện trong student_answer.
5. missing_points chứa criterion cần có nhưng student_answer chưa nêu hoặc nêu chưa đủ.
6. Chấm độc lập từng criterion.
7. total_score phải bằng tổng score trong rubric_scores.
8. Nếu evidence không đủ để xác nhận hoặc bác bỏ một claim, không tự coi claim đó là sai và đặt sufficient_evidence=false.
9. evidence_refs chỉ chứa source_unit_id thực sự được dùng để đánh giá.
10. Phải trả đúng JSON contract dưới đây. Không bỏ field, không đổi kiểu dữ liệu, không thêm văn bản ngoài JSON.

JSON CONTRACT:

{
  "correct_points": [
    "string"
  ],
  "incorrect_points": [
    "string"
  ],
  "missing_points": [
    "string"
  ],
  "rubric_scores": [
    {
      "criterion_id": "string",
      "criterion": "string",
      "score": 0,
      "max_score": 0,
      "reason": "string"
    }
  ],
  "total_score": 0,
  "max_score": 0,
  "sufficient_evidence": true,
  "evidence_refs": [
    "source_unit_id"
  ]
}

rubric_scores bắt buộc là list object theo đúng thứ tự criteria trong rubric.
Không được trả rubric_scores dưới dạng dictionary hoặc list số.
"""


def build_user_content(sample):
    payload = {
        "question": sample["question"],
        "student_answer": sample["student_answer"],
        "evidence": sample["evidence"],
        "rubric": sample["rubric"],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def extract_json(text: str, *, loads=json.loads):
    """
    Parse JSON ngay cả khi model bọc trong markdown code fence.
    """

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    # Trường hợp output chính xác là JSON
    try:
        return loads(text), None
    except json.JSONDecodeError:
        pass

    # Trường hợp model thêm text ngoài JSON
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        candidate = text[start : end + 1]

        try:
            return (
                loads(candidate),
                None,
            )
        except json.JSONDecodeError as exc:
            return (
                None,
                str(exc),
            )

    return (
        None,
        "Không tìm thấy JSON object.",
    )


def load_model(model_path=None, *, local_files_only=False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    model_location = str(model_path) if model_path is not None else MODEL_ID
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=(torch.float16),
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        model_location,
        local_files_only=local_files_only,
        trust_remote_code=True,
    )

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_location,
        local_files_only=local_files_only,
        quantization_config=(quantization_config),
        device_map={"": 0},
        dtype=torch.float16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )

    model.eval()

    # Tránh warning khi do_sample=False
    model.generation_config.do_sample = False
    model.generation_config.temperature = None
    model.generation_config.top_p = None
    model.generation_config.top_k = None

    return tokenizer, model


def generate_text(
    input_messages, tokenizer, model, *, max_input_tokens=None, max_context_tokens=None
):
    import time

    import torch

    inputs = tokenizer.apply_chat_template(
        input_messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )

    input_tokens = inputs["input_ids"].shape[-1]
    if max_input_tokens is not None and input_tokens > max_input_tokens:
        raise ValueError("INPUT_TOKEN_LIMIT")
    actual_context = getattr(model.config, "max_position_embeddings", None)
    context_limit = (
        min(v for v in (actual_context, max_context_tokens) if v is not None)
        if (actual_context is not None or max_context_tokens is not None)
        else None
    )
    if context_limit is not None and input_tokens + MAX_NEW_TOKENS > context_limit:
        raise ValueError("CONTEXT_LIMIT")

    device = model.get_input_embeddings().weight.device

    inputs = {key: value.to(device) for key, value in inputs.items()}

    input_tokens = inputs["input_ids"].shape[-1]

    start = time.perf_counter()

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=(MAX_NEW_TOKENS),
            do_sample=False,
            pad_token_id=(tokenizer.pad_token_id),
            eos_token_id=(model.generation_config.eos_token_id),
        )

    elapsed = time.perf_counter() - start

    generated = outputs[
        0,
        input_tokens:,
    ]

    raw_response = tokenizer.decode(
        generated,
        skip_special_tokens=True,
    ).strip()

    return raw_response, elapsed, input_tokens, int(generated.numel())
