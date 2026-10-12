"""Validation-only Qwen2.5-7B Teaching baseline. Never loads a test split.

GPU dependencies: CUDA torch, transformers>=4.57,<5, accelerate>=1.10,<2,
bitsandbytes>=0.47,<1. Imports and --help require only Python stdlib.
"""

import argparse
import gc
import hashlib
import json
import os
import re
import time
import unicodedata

if __package__:
    from .validate_dataset import ROOT, input_errors, prediction_metrics, rules
else:
    from validate_dataset import ROOT, input_errors, prediction_metrics, rules

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
VALIDATION_FILE = ROOT / "model-training/prepared-data/teaching/teaching_validation_sft.jsonl"
OUTPUT_FILE = ROOT / "model-training/outputs/teaching-baseline/qwen2.5-7b-validation.json"
METRICS = (
    ("json_valid", "JSON", "JSON valid"),
    ("contract_valid", "Contract", "Contract valid"),
    ("strengths_consistency", "Strengths", "Strengths consistency"),
    ("corrections_consistency", "Corrections", "Corrections consistency"),
    ("missing_focus_consistency", "Missing focus", "Missing focus consistency"),
    ("learning_priority_valid", "Learning priority", "Learning priority valid"),
    ("evidence_guard", "Evidence guard", "Evidence guard"),
    ("forbidden_score_fields", "Forbidden score fields", "Forbidden score fields"),
    ("medical_anchor_guard", "Medical anchor guard", "Medical anchor guard"),
    ("learner_context_usage", "Learner context usage", "Learner context usage"),
)


def learner_context_used(payload, prediction):
    """Behavioral lexical proxy with target linkage; no gold wording required.

    A priority is evidence of emphasis when high for remediation/low mastery,
    or medium/low for an improved or mastered focus. Unknown concept mappings
    fail conservatively rather than attributing generic feedback to context.
    """
    lc = payload["learner_context"]
    if not rules.has_context(lc):
        return True  # Caller retains N/A display and excludes it from denominator.
    if not isinstance(prediction, dict):
        return False
    med = payload["medical_evaluation"]
    anchors = med["correct_points"] + med["incorrect_points"] + med["missing_points"]
    priorities = prediction.get("learning_priority", [])
    feedback = prediction.get("feedback_text", "")

    def normalized(text):
        text = unicodedata.normalize("NFD", str(text).casefold()).replace("đ", "d")
        return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c)))

    def linked(text, target):
        # Avoid the validator's generic-pedagogy exemption for target linkage.
        return rules.sim(text, target) >= .45

    def signals(text, kind):
        patterns = {
            "recurring": ("lap lai", "nhieu lan", "tai dien", "gan day", "truoc day", "qua khu", "thuong xuyen"),
            "improved": ("cai thien", "tien bo", "tot hon", "da khac phuc", "da nam vung", "da tien", "on dinh hon"),
            "low": ("chua vung", "chua nam", "con yeu", "muc do thap", "can cung co", "uu tien", "mastery low"),
            "high": ("nam vung", "thanh thao", "muc do cao", "da vung", "duy tri", "mastery high"),
        }
        return any(p in normalized(text) for p in patterns[kind])

    def targets(entry):
        if not isinstance(entry, dict):
            return [entry] if isinstance(entry, str) and entry.strip() else []
        descriptions = [entry[k] for k in ("error_summary", "improvement_summary", "focus", "concept_name", "description")
                        if isinstance(entry.get(k), str) and entry[k].strip()]
        concept = entry.get("concept_id")
        if concept:
            for key in ("recurring_errors", "recent_improvements"):
                for other in lc.get(key, []):
                    if isinstance(other, dict) and other.get("concept_id") == concept:
                        descriptions += [other[k] for k in ("error_summary", "improvement_summary")
                                         if isinstance(other.get(k), str)]
            # Explicit IDs are useful when the focus or feedback names the concept.
            descriptions.append(concept)
        matched = [a for a in anchors if any(linked(a, d) for d in descriptions)]
        return matched or descriptions

    def used(entry, kind):
        relevant = targets(entry)
        if not relevant:
            return False
        for priority in priorities:
            if any(linked(priority["focus"], target) for target in relevant):
                if signals(priority["reason"], kind):
                    return True  # Reason belongs to this specific anchored focus.
                levels = {"high"} if kind in ("recurring", "low") else {"medium", "low"}
                if priority["priority"] in levels:
                    return True
        # A generic 'you improved' sentence alone cannot identify the target.
        for sentence in re.split(r"[.!?;\n]+", feedback):
            if signals(sentence, kind) and any(linked(sentence, target) for target in relevant):
                return True
        return False

    checks = []
    for key, kind in (("recurring_errors", "recurring"), ("recent_improvements", "improved")):
        checks.extend(used(entry, kind) for entry in lc.get(key, []))
    for entry in lc.get("mastery", []):
        if isinstance(entry, dict) and entry.get("level") in ("low", "high"):
            checks.append(used(entry, entry["level"]))
    if not checks and lc.get("recent_attempts_summary"):
        summary = lc["recent_attempts_summary"]
        checks.append(any(
            used({"description": summary}, kind) for kind in ("recurring", "improved", "low", "high")
        ))
    return bool(checks) and all(checks)


def load_validation():
    # Fixed allowlist: no glob, split argument, raw dataset validator, or test access.
    rows = rules.read_jsonl(VALIDATION_FILE)
    if len(rows) != 10 or len({r["sample_id"] for r in rows}) != 10:
        raise ValueError("Locked validation requires 10 unique samples")
    for row in rows:
        qid = rules.qnum_from_sid(row["sample_id"])
        if qid not in {"0005", "0008"}:
            raise ValueError("Sample outside locked validation questions")
        messages = row["messages"]
        if ([m["role"] for m in messages] != ["system", "user", "assistant"]
                or any(not isinstance(m["content"], str) or not m["content"].strip() for m in messages)):
            raise ValueError("Invalid SFT messages")
        payload = json.loads(messages[1]["content"])
        if input_errors({"schema_version": "1.0.0", **payload}):
            raise ValueError("Invalid validation input")
    return rows


def evaluate_prediction(payload, raw):
    try:
        # Strict JSON: markdown/prose is a failure, preserved for manual review.
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Duplicate JSON key: {key}")
                result[key] = value
            return result
        def reject_constant(value):
            raise ValueError(f"Non-standard JSON constant: {value}")
        prediction = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, TypeError) as exc:
        return None, {key: False for key, _, _ in METRICS}, [str(exc)]
    metrics, errors = prediction_metrics(payload, prediction)
    # Override only this baseline metric; locked dataset V5 and other metrics stay intact.
    if metrics["contract_valid"]:
        metrics["learner_context_usage"] = learner_context_used(payload, prediction)
        errors = [error for error in errors if error != "learner_context_usage"]
        if not metrics["learner_context_usage"]:
            errors.append("learner_context_usage")
    return prediction, {"json_valid": True, **metrics}, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    rows = load_validation()
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required; no CPU benchmark fallback")
    tokenizer = model = None
    results = []
    set_seed(42)
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, device_map={"": 0}, dtype=torch.float16,
            low_cpu_mem_usage=True, attn_implementation="sdpa",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
            ),
        )
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
            if prompt_tokens + 1600 > model.config.max_position_embeddings:
                raise ValueError("Context overflow; no silent truncation")
            inputs = {key: value.to(model.get_input_embeddings().weight.device) for key, value in inputs.items()}
            torch.cuda.synchronize()
            start = time.perf_counter()
            with torch.inference_mode():
                output = model.generate(
                    **inputs, max_new_tokens=1600, do_sample=False, temperature=0.0,
                    pad_token_id=tokenizer.pad_token_id,
                )
            torch.cuda.synchronize()
            latency = time.perf_counter() - start
            tokens = output[0, prompt_tokens:]
            raw = tokenizer.decode(tokens, skip_special_tokens=True).strip()
            prediction, metrics, errors = evaluate_prediction(payload, raw)
            context_applicable = rules.has_context(payload["learner_context"])
            results.append({
                "sample_id": row["sample_id"], "raw_prediction": raw,
                "prediction": prediction, "gold_output": json.loads(row["messages"][2]["content"]),
                "input": payload, "metrics": metrics, "errors": errors,
                "learner_context_applicable": context_applicable,
                "latency_seconds": latency, "prompt_tokens": prompt_tokens,
                "generated_tokens": int(tokens.numel()),
                "hit_max_new_tokens": int(tokens.numel()) == 1600,
            })
            print(f"\n[{index}/{len(rows)}] {row['sample_id']}")
            for key, label, _ in METRICS:
                status = "N/A" if key == "learner_context_usage" and not context_applicable else ("PASS" if metrics[key] else "FAIL")
                print(f"{label}: {status}")
        summary = {}
        print("\n=== TEACHING BASELINE SUMMARY ===")
        for key, _, label in METRICS:
            applicable = [r for r in results if key != "learner_context_usage" or r["learner_context_applicable"]]
            summary[key] = {"passed": sum(r["metrics"][key] for r in applicable), "total": len(applicable)}
            print(f"{label}: {summary[key]['passed']}/{summary[key]['total']}")
        average = sum(r["latency_seconds"] for r in results) / len(results)
        summary["average_latency_seconds"] = average
        print(f"Average latency: {average:.4f}s")
        report = {
            "model_id": MODEL_ID, "dataset": str(VALIDATION_FILE.relative_to(ROOT)),
            "dataset_sha256": hashlib.sha256(VALIDATION_FILE.read_bytes()).hexdigest(),
            "total_samples": len(results), "metrics": summary, "cases": results,
            "generation": {"do_sample": False, "temperature": 0, "max_new_tokens": 1600, "seed": 42},
            "environment": {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0)},
            "metric_policy": "Deterministic lexical proxies from Teaching V1-V7; manual review required. No test selection.",
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {OUTPUT_FILE}")
    finally:
        if model is not None:
            del model
        if tokenizer is not None:
            del tokenizer
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
