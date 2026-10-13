"""Teaching QLoRA V1 validation; shares the baseline's exact metric functions.

Requires CUDA torch, transformers>=4.57,<5, peft>=0.17,<1,
accelerate>=1.10,<2 and bitsandbytes>=0.47,<1. Import/--help is offline.
"""

import argparse
import gc
import hashlib
import json
import os
import time

if __package__:
    from . import evaluate_baseline as baseline
else:
    import evaluate_baseline as baseline

ADAPTER_DIR = baseline.ROOT / "model-training/outputs/teaching-qwen2.5-v1/adapter"
OUTPUT_FILE = baseline.ROOT / "model-training/outputs/teaching-qwen2.5-v1/validation_after_finetune.json"
MAX_NEW_TOKENS = 1600  # Same as the unchanged baseline.

# Reuse by identity, including learner_context_usage and strict JSON parsing.
evaluate_prediction = baseline.evaluate_prediction
load_validation = baseline.load_validation
METRICS = baseline.METRICS


def check_adapter():
    config_path = ADAPTER_DIR / "adapter_config.json"
    weights_path = ADAPTER_DIR / "adapter_model.safetensors"
    for path in (config_path, weights_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing/empty adapter artifact: {path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("base_model_name_or_path") != baseline.MODEL_ID:
        raise ValueError("Adapter base model does not match Teaching baseline")
    if config.get("peft_type") != "LORA" or config.get("task_type") != "CAUSAL_LM":
        raise ValueError("Expected a causal-LM LoRA adapter")
    return config


def summarize(results):
    summary = {}
    for key, _, label in METRICS:
        applicable = [r for r in results if key != "learner_context_usage" or r["learner_context_applicable"]]
        summary[key] = {"passed": sum(r["metrics"][key] for r in applicable), "total": len(applicable)}
        print(f"{label}: {summary[key]['passed']}/{summary[key]['total']}")
    summary["average_latency_seconds"] = sum(r["latency_seconds"] for r in results) / len(results)
    print(f"Average latency: {summary['average_latency_seconds']:.4f}s")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if baseline.MODEL_ID != "Qwen/Qwen2.5-7B-Instruct":
        raise ValueError("Teaching V1 requires Qwen/Qwen2.5-7B-Instruct")
    adapter_config = check_adapter()
    rows = load_validation()  # Baseline enforces exactly 10 unique validation samples.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required; no CPU inference fallback")
    tokenizer = base_model = model = None
    results = []
    set_seed(42)
    try:
        # Use the base tokenizer, exactly as baseline; adapter tokenizer cannot
        # silently change the system/user chat formatting during comparison.
        tokenizer = AutoTokenizer.from_pretrained(baseline.MODEL_ID)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        base_model = AutoModelForCausalLM.from_pretrained(
            baseline.MODEL_ID, device_map={"": 0}, dtype=torch.float16,
            low_cpu_mem_usage=True, attn_implementation="sdpa",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
            ),
        )
        model = PeftModel.from_pretrained(base_model, str(ADAPTER_DIR),
                                          is_trainable=False, device_map={"": 0})
        model.eval()
        model.generation_config.do_sample = False
        model.generation_config.temperature = 0.0
        model.generation_config.top_p = None
        model.generation_config.top_k = None
        for index, row in enumerate(rows, 1):
            payload = json.loads(row["messages"][1]["content"])
            inputs = tokenizer.apply_chat_template(
                row["messages"][:2], tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors="pt",
            )
            prompt_tokens = inputs["input_ids"].shape[-1]
            if prompt_tokens + MAX_NEW_TOKENS > model.config.max_position_embeddings:
                raise ValueError("Context overflow; no silent truncation")
            inputs = {key: value.to(model.get_input_embeddings().weight.device) for key, value in inputs.items()}
            torch.cuda.synchronize()
            start = time.perf_counter()
            with torch.inference_mode():
                output = model.generate(
                    **inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                    temperature=0.0, pad_token_id=tokenizer.pad_token_id,
                )
            torch.cuda.synchronize()
            latency = time.perf_counter() - start
            tokens = output[0, prompt_tokens:]
            raw = tokenizer.decode(tokens, skip_special_tokens=True).strip()
            prediction, metrics, errors = evaluate_prediction(payload, raw)
            context_applicable = baseline.rules.has_context(payload["learner_context"])
            results.append({
                "sample_id": row["sample_id"], "raw_prediction": raw, "prediction": prediction,
                "gold_output": json.loads(row["messages"][2]["content"]), "input": payload,
                "metrics": metrics, "errors": errors, "learner_context_applicable": context_applicable,
                "latency_seconds": latency, "prompt_tokens": prompt_tokens,
                "generated_tokens": int(tokens.numel()),
                "hit_max_new_tokens": int(tokens.numel()) == MAX_NEW_TOKENS,
            })
            print(f"\n[{index}/{len(rows)}] {row['sample_id']}")
            for key, label, _ in METRICS:
                status = "N/A" if key == "learner_context_usage" and not context_applicable else ("PASS" if metrics[key] else "FAIL")
                print(f"{label}: {status}")
        print("\n=== TEACHING ADAPTER V1 SUMMARY ===")
        summary = summarize(results)
        report = {
            "model_id": baseline.MODEL_ID, "adapter": str(ADAPTER_DIR.relative_to(baseline.ROOT)),
            "adapter_config": adapter_config,
            "adapter_sha256": hashlib.sha256((ADAPTER_DIR / "adapter_model.safetensors").read_bytes()).hexdigest(),
            "dataset": str(baseline.VALIDATION_FILE.relative_to(baseline.ROOT)),
            "dataset_sha256": hashlib.sha256(baseline.VALIDATION_FILE.read_bytes()).hexdigest(),
            "total_samples": len(results), "metrics": summary, "cases": results,
            "generation": {"do_sample": False, "temperature": 0, "max_new_tokens": MAX_NEW_TOKENS, "seed": 42},
            "environment": {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0)},
            "metric_policy": "Exact evaluate_baseline.evaluate_prediction; manual review required. No test selection.",
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {OUTPUT_FILE}")
    finally:
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
