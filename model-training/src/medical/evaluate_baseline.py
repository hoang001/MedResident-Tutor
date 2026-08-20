import gc
import json
import re
import time
from pathlib import Path

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MAX_NEW_TOKENS = 1200


# ============================================================
# PATHS
# ============================================================

def find_repo_root() -> Path:
    current = Path(__file__).resolve()

    for directory in [current.parent, *current.parents]:
        if (
            (directory / ".git").exists()
            and (directory / "model-training").exists()
        ):
            return directory

    raise RuntimeError("Không tìm thấy repository root.")


ROOT = find_repo_root()

VALIDATION_FILE = (
    ROOT
    / "model-training"
    / "prepared-data"
    / "medical"
    / "medical_validation_sft.jsonl"
)

OUTPUT_DIR = (
    ROOT
    / "model-training"
    / "outputs"
    / "medical-baseline"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "qwen3-4b-validation.json"
)


# ============================================================
# CONTRACT
# ============================================================

REQUIRED_FIELDS = {
    "correct_points",
    "incorrect_points",
    "missing_points",
    "rubric_scores",
    "total_score",
    "max_score",
    "sufficient_evidence",
    "evidence_refs",
}

REQUIRED_RUBRIC_SCORE_FIELDS = {
    "criterion_id",
    "criterion",
    "score",
    "max_score",
    "reason",
}


# ============================================================
# IO
# ============================================================

def read_jsonl(path: Path):
    rows = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line_number, line in enumerate(
            f,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                rows.append(
                    json.loads(line)
                )
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path.name}: JSON lỗi tại "
                    f"dòng {line_number}: {exc}"
                ) from exc

    return rows


# ============================================================
# JSON PARSING
# ============================================================

def extract_json(text: str):
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
        return json.loads(text), None
    except json.JSONDecodeError:
        pass

    # Trường hợp model thêm text ngoài JSON
    start = text.find("{")
    end = text.rfind("}")

    if (
        start >= 0
        and end > start
    ):
        candidate = text[
            start : end + 1
        ]

        try:
            return (
                json.loads(candidate),
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


# ============================================================
# CONTRACT VALIDATION
# ============================================================

def validate_contract(prediction):
    errors = []

    if not isinstance(
        prediction,
        dict,
    ):
        return [
            "Output không phải JSON object."
        ]

    # Check top-level fields
    missing_fields = (
        REQUIRED_FIELDS
        - prediction.keys()
    )

    if missing_fields:
        errors.append(
            "Thiếu fields: "
            + ", ".join(
                sorted(missing_fields)
            )
        )

    # Check list fields
    for field in (
        "correct_points",
        "incorrect_points",
        "missing_points",
        "rubric_scores",
        "evidence_refs",
    ):
        if (
            field in prediction
            and not isinstance(
                prediction[field],
                list,
            )
        ):
            errors.append(
                f"{field} phải là list."
            )

    # Check boolean
    if (
        "sufficient_evidence"
        in prediction
        and not isinstance(
            prediction[
                "sufficient_evidence"
            ],
            bool,
        )
    ):
        errors.append(
            "sufficient_evidence "
            "phải là boolean."
        )

    # Check numeric scores
    for field in (
        "total_score",
        "max_score",
    ):
        if (
            field in prediction
            and not isinstance(
                prediction[field],
                (int, float),
            )
        ):
            errors.append(
                f"{field} phải là số."
            )

    # Check rubric_scores structure
    rubric_scores = prediction.get(
        "rubric_scores"
    )

    if isinstance(
        rubric_scores,
        list,
    ):
        for index, item in enumerate(
            rubric_scores,
            start=1,
        ):
            if not isinstance(
                item,
                dict,
            ):
                errors.append(
                    "rubric_scores"
                    f"[{index}] phải là object."
                )
                continue

            missing = (
                REQUIRED_RUBRIC_SCORE_FIELDS
                - item.keys()
            )

            if missing:
                errors.append(
                    f"rubric_scores[{index}] "
                    "thiếu fields: "
                    + ", ".join(
                        sorted(missing)
                    )
                )

            if (
                "score" in item
                and not isinstance(
                    item["score"],
                    (int, float),
                )
            ):
                errors.append(
                    f"rubric_scores[{index}]"
                    ".score phải là số."
                )

            if (
                "max_score" in item
                and not isinstance(
                    item["max_score"],
                    (int, float),
                )
            ):
                errors.append(
                    f"rubric_scores[{index}]"
                    ".max_score phải là số."
                )

    return errors


# ============================================================
# METRICS
# ============================================================

def rubric_score_map(output):
    """
    Chuyển rubric_scores thành:
    {
        criterion_id: score
    }
    """

    result = {}

    scores = output.get(
        "rubric_scores",
        [],
    )

    if not isinstance(
        scores,
        list,
    ):
        return result

    for item in scores:
        if not isinstance(
            item,
            dict,
        ):
            continue

        criterion_id = item.get(
            "criterion_id"
        )

        score = item.get(
            "score"
        )

        if criterion_id is not None:
            result[
                criterion_id
            ] = score

    return result


def check_score_consistency(
    prediction,
):
    """
    Kiểm tra:

    total_score
    ==
    tổng score trong rubric_scores
    """

    scores = prediction.get(
        "rubric_scores"
    )

    if not isinstance(
        scores,
        list,
    ):
        return False

    total = 0

    for item in scores:
        if not isinstance(
            item,
            dict,
        ):
            return False

        score = item.get(
            "score"
        )

        if not isinstance(
            score,
            (int, float),
        ):
            return False

        total += score

    predicted_total = prediction.get(
        "total_score"
    )

    if not isinstance(
        predicted_total,
        (int, float),
    ):
        return False

    return total == predicted_total


def compare_with_gold(
    prediction,
    gold,
):
    pred_scores = rubric_score_map(
        prediction
    )

    gold_scores = rubric_score_map(
        gold
    )

    return {
        "criterion_scores_exact": (
            bool(gold_scores)
            and pred_scores
            == gold_scores
        ),

        "total_score_exact": (
            prediction.get(
                "total_score"
            )
            == gold.get(
                "total_score"
            )
        ),

        "score_consistent": (
            check_score_consistency(
                prediction
            )
        ),

        "max_score_exact": (
            prediction.get(
                "max_score"
            )
            == gold.get(
                "max_score"
            )
        ),

        "sufficient_evidence_exact": (
            prediction.get(
                "sufficient_evidence"
            )
            == gold.get(
                "sufficient_evidence"
            )
        ),

        # Không yêu cầu cùng thứ tự source ID
        "evidence_refs_exact": (
            set(
                prediction.get(
                    "evidence_refs",
                    [],
                )
            )
            == set(
                gold.get(
                    "evidence_refs",
                    [],
                )
            )
        ),

        "gold_criterion_scores": (
            gold_scores
        ),

        "predicted_criterion_scores": (
            pred_scores
        ),
    }


# ============================================================
# MODEL
# ============================================================

def load_model():
    quantization_config = (
        BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=(
                torch.float16
            ),
            bnb_4bit_use_double_quant=True,
        )
    )

    tokenizer = (
        AutoTokenizer.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
        )
    )

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = (
            tokenizer.eos_token
        )

    model = (
        AutoModelForCausalLM
        .from_pretrained(
            MODEL_ID,
            quantization_config=(
                quantization_config
            ),
            device_map={"": 0},
            dtype=torch.float16,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
    )

    model.eval()

    # Tránh warning khi do_sample=False
    model.generation_config.do_sample = (
        False
    )
    model.generation_config.temperature = (
        None
    )
    model.generation_config.top_p = None
    model.generation_config.top_k = None

    return tokenizer, model


# ============================================================
# INFERENCE
# ============================================================

def run_sample(
    row,
    tokenizer,
    model,
):
    messages = row["messages"]

    # messages[-1] là GOLD assistant.
    # Tuyệt đối không đưa nó vào input.
    input_messages = messages[:-1]

    gold = json.loads(
        messages[-1]["content"]
    )

    inputs = (
        tokenizer.apply_chat_template(
            input_messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
    )

    device = (
        model
        .get_input_embeddings()
        .weight
        .device
    )

    inputs = {
        key: value.to(device)
        for key, value
        in inputs.items()
    }

    input_tokens = (
        inputs["input_ids"]
        .shape[-1]
    )

    start = time.perf_counter()

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=(
                MAX_NEW_TOKENS
            ),
            do_sample=False,
            pad_token_id=(
                tokenizer.pad_token_id
            ),
            eos_token_id=(
                model
                .generation_config
                .eos_token_id
            ),
        )

    elapsed = (
        time.perf_counter()
        - start
    )

    generated = outputs[
        0,
        input_tokens:,
    ]

    raw_response = (
        tokenizer.decode(
            generated,
            skip_special_tokens=True,
        )
        .strip()
    )

    prediction, parse_error = (
        extract_json(
            raw_response
        )
    )

    result = {
        "sample_id": (
            row["sample_id"]
        ),
        "question_id": (
            row["question_id"]
        ),
        "latency_seconds": round(
            elapsed,
            4,
        ),
        "input_tokens": (
            input_tokens
        ),
        "generated_tokens": int(
            generated.numel()
        ),
        "raw_response": (
            raw_response
        ),
        "gold": gold,
        "json_valid": (
            prediction is not None
        ),
        "parse_error": (
            parse_error
        ),
    }

    if prediction is None:
        result.update(
            {
                "prediction": None,
                "contract_valid": False,
                "contract_errors": [
                    "Không parse được JSON."
                ],
                "comparison": None,
            }
        )

        return result

    contract_errors = (
        validate_contract(
            prediction
        )
    )

    result.update(
        {
            "prediction": prediction,
            "contract_valid": (
                not contract_errors
            ),
            "contract_errors": (
                contract_errors
            ),
            "comparison": (
                compare_with_gold(
                    prediction,
                    gold,
                )
            ),
        }
    )

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    rows = read_jsonl(
        VALIDATION_FILE
    )

    print(
        "=== QWEN3 MEDICAL BASELINE ==="
    )
    print(
        "Model:",
        MODEL_ID,
    )
    print(
        "Validation samples:",
        len(rows),
    )

    tokenizer = None
    model = None

    try:
        tokenizer, model = (
            load_model()
        )

        results = []

        for index, row in enumerate(
            rows,
            start=1,
        ):
            print(
                f"\n[{index}/{len(rows)}] "
                f"{row['sample_id']}"
            )

            result = run_sample(
                row,
                tokenizer,
                model,
            )

            results.append(
                result
            )

            print(
                "JSON:",
                "PASS"
                if result["json_valid"]
                else "FAIL",
            )

            print(
                "Contract:",
                "PASS"
                if result[
                    "contract_valid"
                ]
                else "FAIL",
            )

            comparison = result.get(
                "comparison"
            )

            if comparison:
                print(
                    "Criterion scores:",
                    "PASS"
                    if comparison[
                        "criterion_scores_exact"
                    ]
                    else "FAIL",
                )

                print(
                    "Total score:",
                    "PASS"
                    if comparison[
                        "total_score_exact"
                    ]
                    else "FAIL",
                )

                print(
                    "Score consistency:",
                    "PASS"
                    if comparison[
                        "score_consistent"
                    ]
                    else "FAIL",
                )

                print(
                    "Sufficient evidence:",
                    "PASS"
                    if comparison[
                        "sufficient_evidence_exact"
                    ]
                    else "FAIL",
                )

                print(
                    "Evidence refs:",
                    "PASS"
                    if comparison[
                        "evidence_refs_exact"
                    ]
                    else "FAIL",
                )

        # ====================================================
        # SUMMARY
        # ====================================================

        total = len(results)

        json_pass = sum(
            item["json_valid"]
            for item in results
        )

        contract_pass = sum(
            item["contract_valid"]
            for item in results
        )

        criterion_pass = sum(
            bool(
                item["comparison"]
            )
            and item[
                "comparison"
            ][
                "criterion_scores_exact"
            ]
            for item in results
        )

        total_score_pass = sum(
            bool(
                item["comparison"]
            )
            and item[
                "comparison"
            ][
                "total_score_exact"
            ]
            for item in results
        )

        consistency_pass = sum(
            bool(
                item["comparison"]
            )
            and item[
                "comparison"
            ][
                "score_consistent"
            ]
            for item in results
        )

        sufficient_evidence_pass = sum(
            bool(
                item["comparison"]
            )
            and item[
                "comparison"
            ][
                "sufficient_evidence_exact"
            ]
            for item in results
        )

        evidence_refs_pass = sum(
            bool(
                item["comparison"]
            )
            and item[
                "comparison"
            ][
                "evidence_refs_exact"
            ]
            for item in results
        )

        average_latency = (
            sum(
                item[
                    "latency_seconds"
                ]
                for item in results
            )
            / total
            if total
            else 0
        )

        report = {
            "model_id": MODEL_ID,
            "dataset": str(
                VALIDATION_FILE
                .relative_to(ROOT)
            ),
            "total_samples": (
                total
            ),
            "metrics": {
                "json_valid": {
                    "passed": (
                        json_pass
                    ),
                    "total": total,
                },
                "contract_valid": {
                    "passed": (
                        contract_pass
                    ),
                    "total": total,
                },
                "criterion_scores_exact": {
                    "passed": (
                        criterion_pass
                    ),
                    "total": total,
                },
                "total_score_exact": {
                    "passed": (
                        total_score_pass
                    ),
                    "total": total,
                },
                "score_consistency": {
                    "passed": (
                        consistency_pass
                    ),
                    "total": total,
                },
                "sufficient_evidence_exact": {
                    "passed": (
                        sufficient_evidence_pass
                    ),
                    "total": total,
                },
                "evidence_refs_exact": {
                    "passed": (
                        evidence_refs_pass
                    ),
                    "total": total,
                },
                "average_latency_seconds": (
                    round(
                        average_latency,
                        4,
                    )
                ),
            },
            "cases": results,
        }

        OUTPUT_FILE.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            "\n=== BASELINE SUMMARY ==="
        )

        print(
            "JSON valid:",
            f"{json_pass}/{total}",
        )

        print(
            "Contract valid:",
            f"{contract_pass}/{total}",
        )

        print(
            "Criterion scores exact:",
            f"{criterion_pass}/{total}",
        )

        print(
            "Total score exact:",
            f"{total_score_pass}/{total}",
        )

        print(
            "Score consistency:",
            f"{consistency_pass}/{total}",
        )

        print(
            "Sufficient evidence exact:",
            f"{sufficient_evidence_pass}/{total}",
        )

        print(
            "Evidence refs exact:",
            f"{evidence_refs_pass}/{total}",
        )

        print(
            "Average latency:",
            f"{average_latency:.2f}s",
        )

        print(
            "\nSaved:",
            OUTPUT_FILE,
        )

    finally:
        if model is not None:
            del model

        if tokenizer is not None:
            del tokenizer

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()