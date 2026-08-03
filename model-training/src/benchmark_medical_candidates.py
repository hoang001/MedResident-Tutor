
import argparse
import gc
import json
import os
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "model-training" / "outputs" / "candidate-benchmarks"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_model(model: Any = None, tokenizer: Any = None) -> None:
    try:
        if model is not None:
            del model
        if tokenizer is not None:
            del tokenizer
    finally:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except RuntimeError:
                pass


def parse_first_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError("Không tìm thấy object JSON trong output.")
    parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(parsed, dict):
        raise ValueError("Output JSON phải là object.")
    return parsed


def load_text_model(model_id: str):
    if not torch.cuda.is_available():
        raise RuntimeError("Không phát hiện CUDA.")

    token = os.getenv("HF_TOKEN")
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        token=token,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        token=token,
        quantization_config=quantization_config,
        dtype=torch.float16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    model.eval()
    model.generation_config.do_sample = False
    model.generation_config.temperature = None
    model.generation_config.top_p = None
    model.generation_config.top_k = None
    return tokenizer, model


def render_chat(
    tokenizer,
    messages: list[dict[str, str]],
    model_id: str,
    continue_final_message: bool = False,
):
    kwargs: dict[str, Any] = {
        "tokenize": True,
        "return_dict": True,
        "return_tensors": "pt",
    }
    if continue_final_message:
        kwargs["continue_final_message"] = True
    if "Qwen3" in model_id:
        kwargs["enable_thinking"] = False
    return tokenizer.apply_chat_template(messages, **kwargs)


def move_inputs_to_model(inputs: dict[str, Any], model) -> dict[str, Any]:
    device = model.get_input_embeddings().weight.device
    return {
        key: value.to(device) if torch.is_tensor(value) else value
        for key, value in inputs.items()
    }


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(flatten_text(item) for item in value.values())
    return str(value)


CANDIDATES = {
    "qwen3-4b": "Qwen/Qwen3-4B-Instruct-2507",
    "qwen25-7b": "Qwen/Qwen2.5-7B-Instruct",
    "command-r7b": "CohereLabs/c4ai-command-r7b-12-2024",
    "mistral-nemo-12b": "mistralai/Mistral-Nemo-Instruct-2407",
    "deepseek-r1-qwen7b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "gemma2-9b": "google/gemma-2-9b-it",
}

DEFAULT_CANDIDATES = [
    "qwen3-4b",
    "qwen25-7b",
    "command-r7b",
    "mistral-nemo-12b",
    "deepseek-r1-qwen7b",
    "gemma2-9b",
]

TEST_FILE = (
    ROOT
    / "model-training"
    / "sample_data"
    / "medical_candidate_test_cases.json"
)


def build_medical_prompt(case: dict[str, Any]) -> str:
    evidence = json.dumps(case["evidence"], ensure_ascii=False, indent=2)
    rubric = json.dumps(case["rubric"], ensure_ascii=False, indent=2)

    return f"""
Bạn là Medical Model của hệ thống hỗ trợ học tập bác sĩ nội trú.

Chỉ đánh giá dựa trên EVIDENCE và RUBRIC được cung cấp.
Không sử dụng kiến thức bên ngoài.

Quy tắc:
1. correct_points: những ý người học đã nêu đúng và được evidence hỗ trợ.
2. incorrect_points: những điều người học đã khẳng định sai hoặc mâu thuẫn evidence.
3. missing_points: những ý rubric yêu cầu, evidence có cung cấp, nhưng người học chưa nêu hoặc nêu chưa đầy đủ.
4. Không coi một ý là missing nếu evidence không đủ để xác định ý đó.
5. sufficient_evidence=true chỉ khi evidence đủ để chấm toàn bộ rubric.
6. Chấm từng tiêu chí theo đúng rubric.
7. Trả duy nhất một JSON hợp lệ, không Markdown, không giải thích ngoài JSON.
8. evidence chỉ được sao chép hoặc trích từ EVIDENCE, giữ đúng source_id và page.
9. total_score phải bằng tổng score trong rubric_scores.

EVIDENCE:
{evidence}

CÂU HỎI:
{case["question"]}

CÂU TRẢ LỜI NGƯỜI HỌC:
{case["student_answer"]}

RUBRIC:
{rubric}

JSON bắt buộc:
{{
  "correct_points": [],
  "incorrect_points": [],
  "missing_points": [],
  "evidence": [
    {{
      "content": "",
      "source_id": "",
      "page": 0
    }}
  ],
  "rubric_scores": [
    {{
      "criterion_id": "",
      "criterion": "",
      "score": 0,
      "max_score": 0,
      "reason": ""
    }}
  ],
  "total_score": 0,
  "max_score": 0,
  "sufficient_evidence": true
}}
""".strip()


def validate_medical(
    case: dict[str, Any],
    data: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected = case["expected"]

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
            errors.append(f"Thiếu trường {field}.")

    for field in [
        "correct_points",
        "incorrect_points",
        "missing_points",
        "evidence",
        "rubric_scores",
    ]:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} phải là array.")

    if data.get("total_score") != expected.get("total_score"):
        errors.append(
            f"total_score={data.get('total_score')}, "
            f"mong đợi {expected.get('total_score')}."
        )
    if data.get("max_score") != expected.get("max_score"):
        errors.append(
            f"max_score={data.get('max_score')}, "
            f"mong đợi {expected.get('max_score')}."
        )
    if data.get("sufficient_evidence") is not expected.get(
        "sufficient_evidence"
    ):
        errors.append(
            "sufficient_evidence không đúng kỳ vọng."
        )

    for field, expected_count in expected.get(
        "min_counts", {}
    ).items():
        actual = data.get(field, [])
        if not isinstance(actual, list):
            continue
        if expected_count == 0 and len(actual) != 0:
            errors.append(
                f"{field} phải rỗng nhưng có {len(actual)} phần tử."
            )
        elif expected_count > 0 and len(actual) < expected_count:
            errors.append(
                f"{field} cần ít nhất {expected_count} phần tử."
            )

    for field, keywords in expected.get(
        "required_keywords", {}
    ).items():
        content = flatten_text(data.get(field, [])).casefold()
        for keyword in keywords:
            if keyword.casefold() not in content:
                errors.append(
                    f"{field} thiếu từ khóa {keyword!r}."
                )

    rubric_scores = data.get("rubric_scores", [])
    if isinstance(rubric_scores, list):
        numeric_scores = [
            item.get("score")
            for item in rubric_scores
            if isinstance(item, dict)
            and isinstance(item.get("score"), (int, float))
        ]
        if len(numeric_scores) == len(rubric_scores):
            calculated = sum(numeric_scores)
            if calculated != data.get("total_score"):
                errors.append(
                    f"Tổng rubric={calculated} không khớp total_score."
                )

        expected_scores = expected.get("expected_rubric_scores", {})
        for index, rubric_item in enumerate(case.get("rubric", [])):
            criterion_id = rubric_item.get("criterion_id")
            if criterion_id not in expected_scores:
                continue
            if index >= len(rubric_scores):
                errors.append(
                    f"Thiếu rubric score cho {criterion_id}."
                )
                continue
            item = rubric_scores[index]
            actual_score = (
                item.get("score") if isinstance(item, dict) else None
            )
            if actual_score != expected_scores[criterion_id]:
                errors.append(
                    f"{criterion_id} score={actual_score}, "
                    f"mong đợi {expected_scores[criterion_id]}."
                )

    returned_evidence = data.get("evidence", [])
    source_pairs = {
        (item.get("source_id"), item.get("page"))
        for item in case.get("evidence", [])
        if isinstance(item, dict)
    }
    for item in returned_evidence:
        if not isinstance(item, dict):
            errors.append("Mỗi evidence phải là object.")
            continue
        pair = (item.get("source_id"), item.get("page"))
        if pair not in source_pairs:
            errors.append(
                f"Evidence dùng nguồn/trang không tồn tại: {pair}."
            )

    required_any = expected.get("required_source_ids_any")
    if required_any:
        returned_ids = {
            item.get("source_id")
            for item in returned_evidence
            if isinstance(item, dict)
        }
        if not returned_ids.intersection(required_any):
            errors.append(
                "Không giữ lại bất kỳ source_id bắt buộc nào."
            )

    return errors


def generate_medical_case(tokenizer, model, model_id, case):
    prompt = build_medical_prompt(case)
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là Medical Model đánh giá câu trả lời "
                "dựa trên evidence và rubric."
            ),
        },
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": "{"},
    ]
    inputs = render_chat(
        tokenizer,
        messages,
        model_id,
        continue_final_message=True,
    )
    inputs = move_inputs_to_model(inputs, model)
    input_length = inputs["input_ids"].shape[-1]

    start = time.perf_counter()
    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=500,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=model.generation_config.eos_token_id,
        )
    elapsed = time.perf_counter() - start

    generated = output_ids[0, input_length:]
    response = "{" + tokenizer.decode(
        generated,
        skip_special_tokens=True,
    ).strip()
    token_count = int(generated.numel())
    return response, elapsed, token_count


def benchmark_one_model(model_key: str, cases: list[dict[str, Any]]):
    model_id = CANDIDATES[model_key]
    tokenizer = None
    model = None
    result: dict[str, Any] = {
        "model_key": model_key,
        "model_id": model_id,
        "status": "running",
        "cases": [],
    }

    print(f"\n{'=' * 70}")
    print(f"MEDICAL MODEL: {model_id}")
    print(f"{'=' * 70}")

    try:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        load_start = time.perf_counter()
        tokenizer, model = load_text_model(model_id)
        load_seconds = time.perf_counter() - load_start

        latencies: list[float] = []
        token_rates: list[float] = []
        passed_count = 0

        for case in cases:
            case_id = case["case_id"]
            try:
                response, elapsed, token_count = generate_medical_case(
                    tokenizer, model, model_id, case
                )
                latencies.append(elapsed)
                if elapsed > 0:
                    token_rates.append(token_count / elapsed)

                parsed = parse_first_json(response)
                errors = validate_medical(case, parsed)
                passed = not errors
            except Exception as exc:
                response = ""
                parsed = None
                errors = [f"{type(exc).__name__}: {exc}"]
                passed = False
                elapsed = 0.0
                token_count = 0

            if passed:
                passed_count += 1

            print(
                f"{case_id}: {'PASSED' if passed else 'FAILED'} "
                f"| {elapsed:.2f}s | {token_count} tokens"
            )
            for error in errors:
                print(f"  - {error}")

            result["cases"].append(
                {
                    "case_id": case_id,
                    "category": case.get("category"),
                    "passed": passed,
                    "errors": errors,
                    "latency_seconds": round(elapsed, 4),
                    "generated_tokens": token_count,
                    "response": response,
                    "parsed_output": parsed,
                }
            )

        warm_latencies = latencies[1:] if len(latencies) > 1 else latencies
        result.update(
            {
                "status": "completed",
                "passed": passed_count,
                "total": len(cases),
                "pass_rate": (
                    passed_count / len(cases) if cases else 0.0
                ),
                "load_seconds": round(load_seconds, 4),
                "average_latency_seconds": round(
                    sum(latencies) / len(latencies), 4
                ) if latencies else None,
                "average_warm_latency_seconds": round(
                    sum(warm_latencies) / len(warm_latencies), 4
                ) if warm_latencies else None,
                "average_tokens_per_second": round(
                    sum(token_rates) / len(token_rates), 4
                ) if token_rates else None,
                "peak_vram_gb": round(
                    torch.cuda.max_memory_allocated() / 1024**3, 4
                ),
            }
        )

    except Exception as exc:
        result.update(
            {
                "status": "load_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        print(f"LOAD FAILED: {result['error']}")
    finally:
        cleanup_model(model, tokenizer)

    output_path = OUTPUT_DIR / f"medical_{model_key}.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Đã lưu: {output_path}")
    return result


def resolve_candidates(values: list[str]) -> list[str]:
    if values == ["all"]:
        return DEFAULT_CANDIDATES
    unknown = [value for value in values if value not in CANDIDATES]
    if unknown:
        raise ValueError(f"Candidate không hợp lệ: {unknown}")
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_CANDIDATES,
        help="Alias model cần benchmark hoặc 'all'.",
    )
    args = parser.parse_args()

    payload = json.loads(TEST_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    selected = resolve_candidates(args.models)

    print("GPU nhìn thấy:", torch.cuda.device_count())
    print("Danh sách Medical Model:", selected)

    summary = []
    for model_key in selected:
        summary.append(benchmark_one_model(model_key, cases))

    summary_path = OUTPUT_DIR / "medical_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== MEDICAL SUMMARY ===")
    for item in summary:
        print(
            item["model_key"],
            item.get("status"),
            f"{item.get('passed', 0)}/{item.get('total', len(cases))}",
        )


if __name__ == "__main__":
    main()
