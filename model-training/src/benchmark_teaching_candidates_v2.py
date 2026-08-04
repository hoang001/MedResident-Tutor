
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
from transformers import (
    AutoModelForCausalLM,
    AutoProcessor,
    AutoTokenizer,
    BitsAndBytesConfig,
)

ROOT = Path(__file__).resolve().parents[2]
TEST_FILE = ROOT / "model-training" / "sample_data" / "teaching_candidate_test_cases.json"
OUTPUT_DIR = ROOT / "model-training" / "outputs" / "candidate-benchmarks"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATES = {
    "qwen25-7b": "Qwen/Qwen2.5-7B-Instruct",
    "gemma3-4b": "google/gemma-3-4b-it",
}


def cleanup(model=None, processor=None):
    if model is not None:
        del model
    if processor is not None:
        del processor
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch.cuda.ipc_collect()
        except RuntimeError:
            pass


def input_device(model):
    try:
        return model.get_input_embeddings().weight.device
    except Exception:
        for parameter in model.parameters():
            if parameter.device.type != "meta":
                return parameter.device
    return torch.device("cuda:0")


def move_inputs(inputs, device):
    return {
        key: value.to(device) if torch.is_tensor(value) else value
        for key, value in inputs.items()
    }


def quantization_config():
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )


def load_candidate(model_key):
    model_id = CANDIDATES[model_key]
    token = os.getenv("HF_TOKEN")
    qconfig = quantization_config()

    if model_key == "gemma3-4b":
        try:
            from transformers import Gemma3ForConditionalGeneration
            model_cls = Gemma3ForConditionalGeneration
        except ImportError:
            from transformers import AutoModelForMultimodalLM
            model_cls = AutoModelForMultimodalLM

        processor = AutoProcessor.from_pretrained(model_id, token=token)
        model = model_cls.from_pretrained(
            model_id,
            token=token,
            quantization_config=qconfig,
            dtype=torch.float16,
            device_map={"": 0},
            low_cpu_mem_usage=True,
        )
        backend = "gemma3"
    else:
        processor = AutoTokenizer.from_pretrained(model_id, token=token)
        if processor.pad_token_id is None:
            processor.pad_token = processor.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            token=token,
            quantization_config=qconfig,
            dtype=torch.float16,
            device_map={"": 0},
            low_cpu_mem_usage=True,
        )
        backend = "text"

    model.eval()
    model.generation_config.do_sample = False
    model.generation_config.temperature = None
    model.generation_config.top_p = None
    model.generation_config.top_k = None

    return model_id, processor, model, backend


def build_prompt(case):
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

Viết phản hồi hoàn toàn bằng tiếng Việt, tối đa 140 từ.

Quy tắc:
1. Chỉ sử dụng thông tin có trong MEDICAL_OUTPUT.
2. Không tự bổ sung kiến thức y khoa, cơ chế, biến chứng hoặc ví dụ.
3. Ghi nhận phần đúng trước, sau đó chỉ ra phần sai và phần thiếu.
4. Khi sufficient_evidence=false, phải nói rõ chưa đủ bằng chứng hoặc chưa đủ căn cứ để kết luận đầy đủ.
5. Không nhắc đến JSON, model, prompt hoặc quy trình nội bộ.
6. Không mở đầu bằng lời xin lỗi.
7. Không sử dụng câu tiếng Anh.
8. Không lặp lại toàn bộ dữ liệu đầu vào.

CURRICULUM_METADATA:
{metadata}

MEDICAL_OUTPUT:
{medical_output}

Chỉ trả về nội dung phản hồi cho người học.
""".strip()


def prepare_inputs(processor, model, backend, prompt):
    system_text = (
        "Bạn viết phản hồi sư phạm bằng tiếng Việt và không thêm "
        "kiến thức ngoài dữ liệu được cung cấp."
    )

    if backend == "gemma3":
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_text}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            },
        ]
    else:
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": prompt},
        ]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    return move_inputs(inputs, input_device(model))


def tokenizer_of(processor, backend):
    return processor.tokenizer if backend == "gemma3" else processor


def validate(case, response, constraints):
    errors = []
    expected = case.get("expected", {})
    normalized = response.casefold()

    max_words = constraints.get("max_words", 140)
    word_count = len(response.split())
    if word_count > max_words:
        errors.append(f"Phản hồi có {word_count} từ, vượt quá {max_words}.")

    for opening in constraints.get("forbidden_openings", []):
        if normalized.startswith(opening.casefold()):
            errors.append(f"Mở đầu bị cấm: {opening!r}.")

    for keyword in expected.get("required_keywords_all", []):
        if keyword.casefold() not in normalized:
            errors.append(f"Thiếu từ khóa bắt buộc {keyword!r}.")

    required_any = expected.get("required_keywords_any", [])
    if required_any and not any(
        keyword.casefold() in normalized
        for keyword in required_any
    ):
        errors.append(
            "Không chứa bất kỳ từ khóa yêu cầu nào: "
            + ", ".join(required_any)
        )

    for keyword in expected.get("forbidden_keywords", []):
        if keyword.casefold() in normalized:
            errors.append(f"Chứa từ khóa bị cấm {keyword!r}.")

    english_markers = [
        "feedback:",
        "you correctly",
        "please provide",
        "the learner",
        "based on the evaluation",
    ]
    if any(marker in normalized for marker in english_markers):
        errors.append("Phản hồi chứa mẫu câu tiếng Anh.")

    return errors


def generate_case(processor, model, backend, case):
    inputs = prepare_inputs(
        processor,
        model,
        backend,
        build_prompt(case),
    )
    input_length = inputs["input_ids"].shape[-1]
    tokenizer = tokenizer_of(processor, backend)

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
    response = processor.decode(
        generated,
        skip_special_tokens=True,
    ).strip()

    return response, elapsed, int(generated.numel())


def benchmark_model(model_key, cases, constraints):
    model_id = CANDIDATES[model_key]
    processor = None
    model = None

    result = {
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
        model_id, processor, model, backend = load_candidate(model_key)
        load_seconds = time.perf_counter() - load_start

        passed_count = 0
        latencies = []
        token_rates = []

        for case in cases:
            case_id = case["case_id"]
            try:
                response, elapsed, token_count = generate_case(
                    processor,
                    model,
                    backend,
                    case,
                )
                errors = validate(case, response, constraints)
                passed = not errors
                latencies.append(elapsed)
                if elapsed > 0:
                    token_rates.append(token_count / elapsed)
            except Exception as exc:
                response = ""
                elapsed = 0.0
                token_count = 0
                errors = [f"{type(exc).__name__}: {exc}"]
                passed = False

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

        warm = latencies[1:] if len(latencies) > 1 else latencies

        result.update(
            {
                "status": "completed",
                "passed": passed_count,
                "total": len(cases),
                "pass_rate": passed_count / len(cases) if cases else 0.0,
                "load_seconds": round(load_seconds, 4),
                "average_latency_seconds": round(
                    sum(latencies) / len(latencies), 4
                ) if latencies else None,
                "average_warm_latency_seconds": round(
                    sum(warm) / len(warm), 4
                ) if warm else None,
                "average_tokens_per_second": round(
                    sum(token_rates) / len(token_rates), 4
                ) if token_rates else None,
                "peak_vram_gb": round(
                    torch.cuda.max_memory_allocated() / 1024**3,
                    4,
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
        cleanup(model, processor)

    output_path = OUTPUT_DIR / f"teaching_{model_key}.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Đã lưu: {output_path}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(CANDIDATES),
        default=["gemma3-4b", "qwen25-7b"],
    )
    args = parser.parse_args()

    payload = json.loads(TEST_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    constraints = payload.get("global_constraints", {})

    print("GPU nhìn thấy:", torch.cuda.device_count())
    print("Danh sách Teaching Model:", args.models)

    summary = [
        benchmark_model(model_key, cases, constraints)
        for model_key in args.models
    ]

    summary_path = OUTPUT_DIR / "teaching_comparison_v2.json"
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
