"""Teaching schema v1 and deterministic V1-V7 invariants; no model inference."""

import argparse
import json
from collections import Counter
from pathlib import Path

if __package__:
    from . import validate_teaching_dataset as rules
else:
    import validate_teaching_dataset as rules

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "training"
SPLITS = ("train", "validation", "test")
FORBIDDEN = {"score", "total_score", "max_score", "rubric_scores"}


def contract_errors(out):
    errors = []
    if not isinstance(out, dict) or set(out) != rules.REQUIRED_OUTPUT:
        return ["Expected exactly the six Teaching schema v1 fields"]
    if not rules.is_str_list(out["strengths"]) or any(not s.strip() for s in out["strengths"]):
        errors.append("strengths must contain non-empty strings")
    for key, fields in (
        ("corrections", {"incorrect_point", "feedback"}),
        ("missing_focus", {"missing_point", "feedback"}),
        ("learning_priority", {"focus", "priority", "reason"}),
    ):
        if not isinstance(out[key], list):
            errors.append(f"{key} must be a list")
            continue
        for item in out[key]:
            if (not isinstance(item, dict) or set(item) != fields
                    or any(not isinstance(item[f], str) or not item[f].strip() for f in fields)):
                errors.append(f"{key}: invalid item")
            elif key == "learning_priority" and item["priority"] not in rules.ALLOWED_PRIORITY:
                errors.append("Invalid priority")
    if not isinstance(out["feedback_text"], str) or not out["feedback_text"].strip():
        errors.append("feedback_text must be non-empty string")
    fq = out["follow_up_question"]
    if fq is not None and (not isinstance(fq, str) or not fq.strip()):
        errors.append("follow_up_question must be non-empty string or null")
    return errors


def input_errors(inp):
    if not isinstance(inp, dict) or not rules.REQUIRED_INPUT.issubset(inp):
        return ["Missing Teaching input fields"]
    errors = []
    if inp["schema_version"] != "1.0.0":
        errors.append("Unsupported schema_version")
    for key in ("question", "student_answer"):
        if not isinstance(inp[key], str) or not inp[key].strip():
            errors.append(f"{key} must be non-empty string")
    med = inp["medical_evaluation"]
    if not isinstance(med, dict) or not rules.REQUIRED_MED.issubset(med):
        errors.append("Invalid Medical schema")
    else:
        for key in ("correct_points", "incorrect_points", "missing_points", "evidence_refs"):
            if not rules.is_str_list(med[key]):
                errors.append(f"Invalid Medical {key}")
        if type(med["sufficient_evidence"]) is not bool:
            errors.append("sufficient_evidence must be boolean")
        for key in ("total_score", "max_score"):
            if type(med[key]) not in (int, float):
                errors.append(f"Invalid {key}")
        rubric = med["rubric_scores"]
        if not isinstance(rubric, list) or any(
            not isinstance(r, dict)
            or any(type(r.get(k)) not in (int, float) for k in ("score", "max_score"))
            or any(not isinstance(r.get(k), str) for k in ("criterion_id", "criterion", "reason"))
            for r in rubric
        ):
            errors.append("Invalid rubric_scores")
    lc = inp["learner_context"]
    if not isinstance(lc, dict) or not rules.REQUIRED_LC.issubset(lc):
        errors.append("Invalid learner_context")
    elif (any(not isinstance(lc[k], list) for k in ("mastery", "recurring_errors", "recent_improvements"))
          or (lc["recent_attempts_summary"] is not None and not isinstance(lc["recent_attempts_summary"], str))):
        errors.append("Invalid learner_context field types")
    meta = inp["metadata"]
    if not isinstance(meta, dict) or not rules.REQUIRED_META.issubset(meta):
        errors.append("Invalid metadata")
    elif (meta["course_group"] is not None or meta["specialty_level"] is not None
          or not rules.is_str_list(meta["concept_ids"])
          or meta["topic_id"] in meta["concept_ids"]):
        errors.append("Invalid metadata taxonomy/concept_ids")
    return errors


def learner_errors(inp, out):
    lc = inp["learner_context"]
    if not rules.has_context(lc):
        return []
    errors = []
    med = inp["medical_evaluation"]
    blob = rules.norm(out["feedback_text"] + " " + " ".join(p["reason"] for p in out["learning_priority"]))
    if (med["incorrect_points"] or med["missing_points"]) and not out["learning_priority"]:
        errors.append("Context requires remediation priority")
    for key, marker in (("recurring_errors", "lặp"), ("recent_improvements", "cải thiện")):
        if lc[key] and marker not in blob:
            errors.append(f"{key} not reflected")
    levels = {x.get("level") for x in lc["mastery"] if isinstance(x, dict)}
    if levels & {"low", "high"} and not lc["recurring_errors"] and not lc["recent_improvements"] and "mastery" not in blob:
        errors.append("Mastery not reflected")
    return errors


def prediction_metrics(inp, out):
    """Rule-based proxies, not a proof of clinical factuality; manual review required."""
    med = inp["medical_evaluation"]
    keys = ("contract_valid", "strengths_consistency", "corrections_consistency",
            "missing_focus_consistency", "learning_priority_valid", "evidence_guard",
            "forbidden_score_fields", "medical_anchor_guard", "learner_context_usage")
    metrics = dict.fromkeys(keys, False)
    metrics["forbidden_score_fields"] = not bool(FORBIDDEN & set(rules.walk_keys(out)))
    errors = contract_errors(out)
    if errors:
        return metrics, errors
    metrics["contract_valid"] = True
    unmatched = list(med["correct_points"])
    strengths_ok = len(unmatched) == len(out["strengths"])
    for text in out["strengths"]:
        if not unmatched:
            strengths_ok = False
            break
        best = max(range(len(unmatched)), key=lambda i: rules.sim(text, unmatched[i]))
        if rules.sim(text, unmatched[best]) < .45:
            strengths_ok = False
        unmatched.pop(best)
    metrics["strengths_consistency"] = strengths_ok
    metrics["corrections_consistency"] = Counter(c["incorrect_point"] for c in out["corrections"]) == Counter(med["incorrect_points"])
    metrics["missing_focus_consistency"] = Counter(c["missing_point"] for c in out["missing_focus"]) == Counter(med["missing_points"])
    anchors = rules.factual_anchors(med)
    remediation = med["incorrect_points"] + med["missing_points"]
    priorities = out["learning_priority"]
    metrics["learning_priority_valid"] = (
        (not remediation or bool(priorities))
        and all(max((rules.sim(p["focus"], a) for a in remediation or med["correct_points"]), default=0) >= .42 for p in priorities)
        and len({rules.norm(p["focus"]) for p in priorities}) == len(priorities)
    )
    metrics["learner_context_usage"] = not learner_errors(inp, out)
    if rules.has_context(inp["learner_context"]):
        context_text = rules.norm(out["feedback_text"] + " " + " ".join(p["reason"] for p in priorities))
        metrics["learner_context_usage"] = metrics["learner_context_usage"] and any(
            marker in context_text for marker in
            ("learner_context", "learner context", "mastery", "lặp", "cải thiện", "tiến bộ", "gần đây", "lịch sử")
        )
    text = rules.norm(out["feedback_text"])
    metrics["evidence_guard"] = med["sufficient_evidence"] or (
        any(marker in text for marker in ("chưa đủ", "không đủ", "chưa có đủ", "chưa thể kết luận"))
        and metrics["corrections_consistency"]
    )
    checks = [rules.anchor_ok(s, med["correct_points"], .45) for s in out["strengths"]]
    checks += [rules.anchor_ok(c["feedback"], anchors, .35) for c in out["corrections"]]
    checks += [rules.anchor_ok(c["feedback"], anchors, .30) for c in out["missing_focus"]]
    if out["follow_up_question"]:
        checks.append(rules.anchor_ok(out["follow_up_question"], anchors, .30))
    # Keep locked V6 coverage/thresholds. Free-form feedback and priority reasons
    # require manual review: generic pedagogy is not a medical factual claim.
    metrics["medical_anchor_guard"] = all(checks)
    return metrics, [key for key, passed in metrics.items() if not passed]


def validate(data_dir=DATA_DIR):
    rows = {split: rules.read_jsonl(data_dir / f"teaching_{split}.jsonl") for split in SPLITS}
    errors = []
    def fail(layer, split, sid, message):
        errors.append({"layer": layer, "split": split, "sample_id": sid, "message": message})
    med_ref = {}
    source_available = False
    for split in ("train", "validation"):
        path = data_dir / f"medical_{split}.jsonl"
        if path.exists():
            source_available = True
            med_ref.update({r["sample_id"]: r for r in rules.read_jsonl(path)})
    seen, cases = set(), {}
    qsets, case_sets = {}, {}
    for split, samples in rows.items():
        qsets[split], case_sets[split] = set(), set()
        if not samples:
            fail("V1", split, "<file>", "Empty split")
        for row in samples:
            sid = row.get("sample_id", "") if isinstance(row, dict) else ""
            if not isinstance(sid, str) or not rules.sample_med_id(sid):
                fail("V1", split, str(sid), "Invalid sample_id")
                continue
            if sid in seen:
                fail("V7", split, sid, "Duplicate sample_id")
            seen.add(sid)
            mid, qid = rules.sample_med_id(sid), rules.qnum_from_sid(sid)
            qsets[split].add(qid)
            case_sets[split].add(mid)
            if qid in rules.LOCKED_MEDICAL_TEST_QIDS:
                fail("V7", split, sid, f"Locked Medical test Q_{qid} forbidden")
            if set(row) != {"sample_id", "input", "gold_output"}:
                fail("V1", split, sid, "Invalid top-level fields")
                continue
            inp, out = row["input"], row["gold_output"]
            schema = input_errors(inp)
            for message in schema:
                fail("V1", split, sid, message)
            output_schema = contract_errors(out)
            for message in output_schema:
                fail("V2", split, sid, message)
            if schema or output_schema:
                continue
            med = inp["medical_evaluation"]
            metrics, _ = prediction_metrics(inp, out)
            for key in ("strengths_consistency", "corrections_consistency", "missing_focus_consistency"):
                if not metrics[key]:
                    fail("V3", split, sid, key)
            if not metrics["forbidden_score_fields"]:
                fail("V4", split, sid, "Forbidden score fields")
            for key in ("score", "max_score"):
                total_key = "total_score" if key == "score" else "max_score"
                if med[total_key] != sum(r[key] for r in med["rubric_scores"]):
                    fail("V4", split, sid, f"Medical {total_key} inconsistent")
            if source_available:
                ref = med_ref.get(mid)
                if ref is None or med != ref["gold_output"] or inp["question"] != ref["question"]:
                    fail("V4", split, sid, "Immutable source Medical mismatch/missing")
                elif sid.endswith("_V01") and inp["student_answer"] != ref["student_answer"]:
                    fail("V4", split, sid, "V01 answer differs from Medical source")
            if mid in cases and cases[mid] != med:
                fail("V5", split, sid, "Learner variant changed Medical evaluation")
            cases[mid] = med
            for message in learner_errors(inp, out):
                fail("V5", split, sid, message)
            # Preserve exactly the locked validator's V6 thresholds/coverage.
            anchors = rules.factual_anchors(med)
            texts = [(s, med["correct_points"], .45) for s in out["strengths"]]
            texts += [(c["feedback"], anchors, .35) for c in out["corrections"]]
            texts += [(c["feedback"], anchors, .30) for c in out["missing_focus"]]
            if out["follow_up_question"]:
                texts.append((out["follow_up_question"], anchors, .30))
            if not all(rules.anchor_ok(t, a, threshold) for t, a, threshold in texts):
                fail("V6", split, sid, "Unanchored medical text")
    for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
        for shared in qsets[a] & qsets[b]:
            fail("V7", f"{a}<->{b}", shared, "Question leakage")
        for shared in case_sets[a] & case_sets[b]:
            fail("V7", f"{a}<->{b}", shared, "Case leakage")
    return rows, errors, source_available


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    rows, errors, source_available = validate(args.data_dir)
    print("=== Teaching Dataset Validator v1 ===")
    print("Test: schema/invariants/leakage only. Medical test is never loaded.")
    print("Medical source alignment: " + ("checked" if source_available else "SKIPPED (source unavailable)"))
    for layer in (f"V{i}" for i in range(1, 8)):
        print(f"{layer}: {'FAIL' if any(e['layer'] == layer for e in errors) else 'PASS'}")
    print("Counts: " + ", ".join(f"{k}={len(v)}" for k, v in rows.items()))
    for error in errors:
        print(json.dumps(error, ensure_ascii=False))
    print("OVERALL: " + ("FAIL" if errors else "PASS"))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
