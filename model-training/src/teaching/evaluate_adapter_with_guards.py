"""Original-prompt adapter inference followed by deterministic Teaching guards."""

import builtins
import json
from types import FunctionType

if __package__:
    from . import evaluate_adapter as adapter
    from .apply_teaching_guards import apply_teaching_guards, SIMILARITY_THRESHOLD, AMBIGUITY_MARGIN
else:
    import evaluate_adapter as adapter
    from apply_teaching_guards import apply_teaching_guards, SIMILARITY_THRESHOLD, AMBIGUITY_MARGIN

OUTPUT_FILE = adapter.baseline.ROOT / "model-training/outputs/teaching-qwen2.5-v1/validation_with_guards.json"


def make_runner(records):
    def evaluate_guarded(payload, raw):
        original, before_metrics, before_errors = adapter.evaluate_prediction(payload, raw)
        # Do not repair malformed JSON or an invalid contract into an artificial PASS.
        if before_metrics["contract_valid"]:
            guarded = apply_teaching_guards(payload, original)
            prediction, metrics, errors = adapter.evaluate_prediction(
                payload, json.dumps(guarded, ensure_ascii=False),
            )
        else:
            prediction, metrics, errors = original, before_metrics, before_errors
        records.append({"prediction_before_guards": original,
                        "metrics_before_guards": before_metrics, "errors_before_guards": before_errors,
                        "guard_changed": prediction != original})
        return prediction, metrics, errors

    def print_guarded(*args, **kwargs):
        builtins.print(*(s.replace("=== TEACHING ADAPTER V1 SUMMARY ===",
                                  "=== TEACHING ADAPTER V1 + GUARDS SUMMARY ===")
                         if isinstance(s, str) else s for s in args), **kwargs)

    # Exact unchanged adapter runner; original validation loader and messages.
    namespace = dict(adapter.main.__globals__)
    namespace.update(evaluate_prediction=evaluate_guarded, OUTPUT_FILE=OUTPUT_FILE,
                     print=print_guarded, __doc__=__doc__)
    return FunctionType(adapter.main.__code__, namespace, "run_with_guards",
                        adapter.main.__defaults__, adapter.main.__closure__)


def main():
    records = []
    make_runner(records)()
    report = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    if len(records) != len(report["cases"]):
        raise RuntimeError("Guard audit/sample count mismatch")
    for case, audit in zip(report["cases"], records):
        case.update(audit)
    report["guard_policy"] = {
        "editable_fields": ["learning_priority", "feedback_text"],
        "mapping": "unique normalized exact/whole-point substring, then token Jaccard",
        "similarity_threshold": SIMILARITY_THRESHOLD, "ambiguity_margin": AMBIGUITY_MARGIN,
        "prompt": "original unchanged", "metrics": "unchanged baseline implementation",
    }
    OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
