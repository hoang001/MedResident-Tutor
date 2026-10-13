"""LOCKED one-time Teaching test. Preflight failures do not consume the run.

No model selection, tuning, fallback or automatic retry is permitted.
"""

import builtins
import json
import os
from types import FunctionType, SimpleNamespace

if __package__:
    from . import evaluate_adapter_with_guards as guarded
else:
    import evaluate_adapter_with_guards as guarded

adapter = guarded.adapter
TEST_FILE = adapter.baseline.ROOT / "model-training/prepared-data/teaching/teaching_test_sft.jsonl"
OUTPUT_FILE = adapter.baseline.ROOT / "model-training/outputs/teaching-qwen2.5-v1/test_with_guards.json"
RUN_MARKER = OUTPUT_FILE.with_suffix(".started")


def ensure_unlocked():
    if RUN_MARKER.exists():
        # Legacy markers and malformed state also fail closed.
        raise FileExistsError("Locked test state already exists (STARTED/COMPLETED); refusing rerun")
    if OUTPUT_FILE.exists():
        raise FileExistsError("Locked test report already exists; refusing repeat evaluation")


def start_run():
    ensure_unlocked()
    with RUN_MARKER.open("x", encoding="utf-8") as stream:
        json.dump({"status": "STARTED"}, stream)
        stream.flush()
        os.fsync(stream.fileno())


def complete_run():
    temporary = RUN_MARKER.with_suffix(".completed.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump({"status": "COMPLETED"}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, RUN_MARKER)


def check_contexts(tokenizer, model, rows):
    # Only tokenize inference prompts. Never decode/inspect assistant gold here.
    for row in rows:
        inputs = tokenizer.apply_chat_template(
            row["messages"][:2], tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors="pt",
        )
        if inputs["input_ids"].shape[-1] + adapter.MAX_NEW_TOKENS > model.config.max_position_embeddings:
            raise ValueError("Locked test context overflow; no silent truncation")


def arm_inference(model):
    generate = model.generate
    started = False
    def generate_locked(*args, **kwargs):
        nonlocal started
        if not started:
            start_run()  # Immediately before the first model.generate invocation.
            started = True
        return generate(*args, **kwargs)
    model.generate = generate_locked
    return model


def load_locked_test():
    # Single fixed path; never discover, concatenate or slice dataset splits.
    rows = adapter.baseline.rules.read_jsonl(TEST_FILE)
    if len(rows) != 10:
        raise ValueError(f"Locked test requires exactly 10 samples, got {len(rows)}")
    ids = [r.get("sample_id") if isinstance(r, dict) else None for r in rows]
    if any(not isinstance(sid, str) or not sid.strip() for sid in ids):
        raise ValueError("Locked test sample_id must be a non-empty string")
    if len(set(ids)) != 10:
        raise ValueError("Locked test requires unique sample_id values")
    for row in rows:
        messages = row.get("messages")
        if (not isinstance(messages, list) or len(messages) != 3
                or any(not isinstance(m, dict) for m in messages)
                or [m.get("role") for m in messages] != ["system", "user", "assistant"]
                or any(not isinstance(m.get("content"), str) or not m["content"].strip() for m in messages)):
            raise ValueError("Invalid locked test SFT messages")
        payload = json.loads(messages[1]["content"])
        if not isinstance(payload, dict) or adapter.baseline.input_errors({"schema_version": "1.0.0", **payload}):
            raise ValueError("Invalid locked test input")
    return rows


def make_runner(records):
    original = guarded.make_runner(records)
    namespace = dict(original.__globals__)
    # Adapter runner refers to baseline.VALIDATION_FILE for provenance only.
    # An isolated namespace changes that path without touching baseline module.
    baseline_view = SimpleNamespace(**vars(adapter.baseline))
    baseline_view.VALIDATION_FILE = TEST_FILE
    cache = {}
    def load_preflight():
        rows = load_locked_test()
        cache["rows"] = rows
        return rows
    def import_preflight(name, globals=None, locals=None, fromlist=(), level=0):
        module = builtins.__import__(name, globals, locals, fromlist, level)
        if name == "transformers":
            class TokenizerLoader:
                @staticmethod
                def from_pretrained(*args, **kwargs):
                    tokenizer = module.AutoTokenizer.from_pretrained(*args, **kwargs)
                    cache["tokenizer"] = tokenizer
                    return tokenizer
            return SimpleNamespace(**{**vars(module), "AutoTokenizer": TokenizerLoader})
        if name == "peft":
            class AdapterLoader:
                @staticmethod
                def from_pretrained(*args, **kwargs):
                    model = module.PeftModel.from_pretrained(*args, **kwargs)
                    check_contexts(cache["tokenizer"], model, cache["rows"])
                    return arm_inference(model)
            return SimpleNamespace(**{**vars(module), "PeftModel": AdapterLoader})
        return module
    def print_locked(*args, **kwargs):
        builtins.print(*(s.replace("=== TEACHING ADAPTER V1 SUMMARY ===",
                                  "=== TEACHING LOCKED TEST V1 + GUARDS SUMMARY ===")
                         if isinstance(s, str) else s for s in args), **kwargs)
    namespace.update(load_validation=load_preflight, OUTPUT_FILE=OUTPUT_FILE,
                     baseline=baseline_view, print=print_locked, __doc__=__doc__,
                     __builtins__={**vars(builtins), "__import__": import_preflight})
    return FunctionType(original.__code__, namespace, "run_locked_test",
                        original.__defaults__, original.__closure__)


def main():
    ensure_unlocked()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = []
    make_runner(records)()
    report = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    if len(records) != 10 or len(report["cases"]) != 10:
        raise RuntimeError("Locked test report/audit count mismatch")
    for case, audit in zip(report["cases"], records):
        case.update(audit)
        case["prediction_after_guards"] = case["prediction"]
        case["metrics_after_guards"] = case["metrics"]
        case["errors_after_guards"] = case["errors"]
    report["guard_policy"] = {
        "editable_fields": ["learning_priority", "feedback_text"],
        "mapping": "unique normalized exact/whole-point substring, then token Jaccard",
        "similarity_threshold": guarded.SIMILARITY_THRESHOLD,
        "ambiguity_margin": guarded.AMBIGUITY_MARGIN,
        "prompt": "original unchanged", "metrics": "unchanged baseline implementation",
    }
    report["locked_test"] = True
    report["selection_policy"] = "Selection closed before execution; no tuning, fallback or candidate selection from test."
    with OUTPUT_FILE.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    complete_run()


if __name__ == "__main__":
    main()
