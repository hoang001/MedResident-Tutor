"""Evaluate the Medical LoRA adapter using the locked baseline validation protocol."""

import argparse
import gc
import json
from pathlib import Path


# Report key, baseline comparison key, summary label.
COMPARISON_METRICS = (
    ("criterion_scores_exact", "criterion_scores_exact", "Criterion scores exact"),
    ("total_score_exact", "total_score_exact", "Total score exact"),
    ("score_consistency", "score_consistent", "Score consistency"),
    ("sufficient_evidence_exact", "sufficient_evidence_exact", "Sufficient evidence exact"),
    ("evidence_refs_exact", "evidence_refs_exact", "Evidence refs exact"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapter-dir", type=Path,
        default=Path("model-training/outputs/medical-qwen3-pilot/adapter"),
        help="Adapter directory; relative paths resolve from repository root",
    )
    parser.add_argument(
        "--output-file", type=Path,
        default=Path("model-training/outputs/medical-qwen3-pilot/validation_after_finetune.json"),
        help="Report file; relative paths resolve from repository root",
    )
    cli = parser.parse_args()

    import torch
    from peft import PeftModel

    if not torch.cuda.is_available():
        raise RuntimeError("Cần GPU CUDA để đánh giá Medical LoRA adapter.")

    # Support both direct script execution and python -m src.medical.evaluate_adapter.
    if __package__:
        from . import evaluate_baseline as baseline
    else:
        import evaluate_baseline as baseline

    root = baseline.find_repo_root()
    adapter_dir = cli.adapter_dir if cli.adapter_dir.is_absolute() else root / cli.adapter_dir
    output_file = cli.output_file if cli.output_file.is_absolute() else root / cli.output_file
    output_dir = output_file.parent

    if baseline.MODEL_ID != "Qwen/Qwen3-4B-Instruct-2507":
        raise ValueError("Base model không khớp Medical pilot đã khóa.")
    if not (adapter_dir / "adapter_config.json").is_file():
        raise FileNotFoundError(f"Không tìm thấy LoRA adapter: {adapter_dir}")

    # Reuse the exact validation path and reader; never discover other splits.
    rows = baseline.read_jsonl(baseline.VALIDATION_FILE)
    if len(rows) != 8 or len({row["sample_id"] for row in rows}) != 8:
        raise ValueError("Validation đã khóa phải có đúng 8 samples với ID duy nhất.")

    print("=== QWEN3 MEDICAL ADAPTER VALIDATION ===")
    print("Model:", baseline.MODEL_ID)
    print("Adapter:", adapter_dir)
    print("Validation samples:", len(rows))

    tokenizer = None
    base_model = None
    model = None
    try:
        # Baseline loader: GPU 0, 4-bit NF4, float16, double quantization.
        # Keep the base tokenizer and generation settings identical to baseline.
        tokenizer, base_model = baseline.load_model()
        model = PeftModel.from_pretrained(
            base_model,
            str(adapter_dir),
            is_trainable=False,
            device_map={"": 0},
        )
        model.eval()

        results = []
        for index, row in enumerate(rows, start=1):
            print(f"\n[{index}/{len(rows)}] {row['sample_id']}")
            # Reuse prompt, decoding, JSON parser, contract checks and all metrics.
            result = baseline.run_sample(row, tokenizer, model)
            results.append(result)
            print("JSON:", "PASS" if result["json_valid"] else "FAIL")
            print("Contract:", "PASS" if result["contract_valid"] else "FAIL")
            comparison = result.get("comparison")
            if comparison:
                for _, key, label in COMPARISON_METRICS:
                    print(f"{label}:", "PASS" if comparison[key] else "FAIL")

        total = len(results)
        metrics = {
            key: {"passed": sum(item[key] for item in results), "total": total}
            for key in ("json_valid", "contract_valid")
        }
        for report_key, comparison_key, _ in COMPARISON_METRICS:
            metrics[report_key] = {
                "passed": sum(
                    bool(item["comparison"]) and item["comparison"][comparison_key]
                    for item in results
                ),
                "total": total,
            }
        average_latency = sum(item["latency_seconds"] for item in results) / total
        metrics["average_latency_seconds"] = round(average_latency, 4)

        # Same report structure as baseline, plus adapter provenance.
        report = {
            "model_id": baseline.MODEL_ID,
            "adapter": str(
                adapter_dir.relative_to(root) if adapter_dir.is_relative_to(root) else adapter_dir
            ),
            "dataset": str(baseline.VALIDATION_FILE.relative_to(root)),
            "total_samples": total,
            "metrics": metrics,
            "cases": results,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )

        print("\n=== ADAPTER SUMMARY ===")
        for key, label in (
            ("json_valid", "JSON valid"),
            ("contract_valid", "Contract valid"),
            *((key, label) for key, _, label in COMPARISON_METRICS),
        ):
            print(f"{label}:", f"{metrics[key]['passed']}/{total}")
        print("Average latency:", f"{average_latency:.2f}s")
        print("\nSaved:", output_file)
    finally:
        # Both references must be released because PEFT wraps the base in-place.
        if model is not None:
            del model
        if base_model is not None:
            del base_model
        if tokenizer is not None:
            del tokenizer
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
