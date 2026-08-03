
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
    "gemma2-2b": "google/gemma-2-2b-it",
    "mistral-nemo-12b": "mistralai/Mistral-Nemo-Instruct-2407",
    "vistral-7b": "Viet-Mistral/Vistral-7B-Chat",
}

DEFAULT_CANDIDATES = [
    "qwen3-4b",
    "gemma2-2b",
]

TEST_FILE = (
    ROOT
    / "model-training"
    / "sample_data"
    / "teaching_candidate_test_cases.json"
)


def build_teaching_prompt(case: dict[str, Any]) -> str:
    medical_output = json.dumps(
        case["medical_output"],
        ensure_ascii=False,
        indent=2,
    )
    metadata = json.dumps(
        case.get("curriculum_metadata", {}),
        ensure_ascii=False,
        indent=2,
    )
    return f"""
Bạn là Teaching Model hỗ trợ bác sĩ nội trú.

Viết phản hồi bằng tiếng Việt, tối đa 140 từ.

Quy tắc:
1. Chỉ được sử dụng thông tin có trong MEDICAL_OUTPUT.
2. Không tự bổ sung kiến thức y khoa, cơ chế, biến chứng hoặc ví dụ.
3. Ghi nhận phần đúng trước, sau đó chỉ ra phần sai và phần thiếu.
4. Khi sufficient_evidence=false, phải nói rõ chưa đủ căn cứ để kết luận đầy đủ.
5. Không nhắc đến JSON, model, prompt hoặc quy trình nội bộ.
6. Không mở đầu bằng lời xin lỗi.
7. Không lặp lại toàn bộ dữ liệu đầu vào.

CURRICULUM_METADATA:
{metadata}

MEDICAL_OUTPUT:
{medical_output}

Chỉ trả về nội dung phản hồi cho người học.
""".strip()


def validate_teaching(
    case: dict[str, Any],
    response: str,
    max_words: int,
    forbidden_openings: list[str],
) -> list[str]:
    errors: list[str] = []
    expected = case.get("expected", {})
    normalized = response.casefold()

    word_count = len(response.split())
    if word_count > max_words:
        errors.append(
            f"Phản hồi có {word_count} từ, vượt quá {max_words}."
        )

    for opening in forbidden_openings:
        if normalized.startswith(opening.casefold()):
            errors.append(f"Mở đầu bị cấm: {opening!r}.")

    for keyword in expected.get("required_keywords_all", []):
        if keyword.casefold() not in normalized:
            errors.append(f"Thiếu từ khóa bắt buộc {keyword!r}.")

    required_any = expected.get("required_keywords_any", [])
    if required_any and not any(
        keyword.casefold() in normalized for keyword in required_any
    ):
        errors.append(
            "Không chứa bất kỳ từ khóa yêu cầu nào: "
            + ", ".join(required_any)
        )

    for keyword in expected.get("forbidden_keywords", []):
        if keyword.casefold() in normalized:
            errors.append(f"Chứa từ khóa bị cấm {keyword!r}.")

    common_english_markers = [
        "feedback:",
        "you correctly",
        "please provide",
        "the learner",
        "based on the evaluation",
    ]
    if any(marker in normalized for marker in common_english_markers):
        errors.append("Phản hồi chứa mẫu câu tiếng Anh.")

    return errors


def generate_teaching_case(tokenizer, model, model_id, case):
    prompt = build_teaching_prompt(case)
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn viết phản hồi sư phạm bằng tiếng Việt và "
                "không thêm kiến thức ngoài dữ liệu được cung cấp."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    inputs = render_chat(tokenizer, messages, model_id)
    inputs = move_inputs_to_model(inputs, model)
    input_length = inputs["input_ids"].shape[-1]

    start = time.perf_counter()
    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=220,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=model.generation_config.eos_token_id,
        )
    elapsed = time.perf_counter() - start
    generated = output_ids[0, input_length:]
    response = tokenizer.decode(
        generated,
        skip_special_tokens=True,
    ).strip()
    return response, elapsed, int(generated.numel())


def benchmark_one_model(
    model_key: str,
    cases: list[dict[str, Any]],
    constraints: dict[str, Any],
):
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
    print(f"TEACHING MODEL: {model_id}")
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
                response, elapsed, token_count = generate_teaching_case(
                    tokenizer, model, model_id, case
                )
                latencies.append(elapsed)
                if elapsed > 0:
                    token_rates.append(token_count / elapsed)

                errors = validate_teaching(
                    case,
                    response,
                    constraints.get("max_words", 140),
                    constraints.get("forbidden_openings", []),
                )
                passed = not errors
            except Exception as exc:
                response = ""
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

    output_path = OUTPUT_DIR / f"teaching_{model_key}.json"
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
    constraints = payload.get("global_constraints", {})
    selected = resolve_candidates(args.models)

    print("GPU nhìn thấy:", torch.cuda.device_count())
    print("Danh sách Teaching Model:", selected)

    summary = []
    for model_key in selected:
        summary.append(
            benchmark_one_model(model_key, cases, constraints)
        )

    summary_path = OUTPUT_DIR / "teaching_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== TEACHING SUMMARY ===")
    for item in summary:
        print(
            item["model_key"],
            item.get("status"),
            f"{item.get('passed', 0)}/{item.get('total', len(cases))}",
        )


if __name__ == "__main__":
    main()
