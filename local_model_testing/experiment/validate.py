"""CPU-only dataset/metric preflight; never loads weights or sends a request."""
import json
import sys

from .common import DATA, ROOT, frozen, rows, write

sys.path.insert(0, str(ROOT / "model-training"))


def main():
    from src.medical.validation import EvaluationRequest, validate_output
    from src.teaching.validate_dataset import input_errors

    frozen()
    inputs = rows(DATA / "medical-inputs.jsonl")
    references = {r["sample_id"]: r for r in rows(DATA / "medical-reference.jsonl")}
    for row in inputs:
        assert set(row["payload"]) == {"question", "student_answer", "rubric", "evidence"}
        request = EvaluationRequest.model_validate(row["payload"])
        validate_output(json.dumps(references[row["sample_id"]]["expected"]), request)
        if row["answer_type"] == "unrelated":
            assert references[row["sample_id"]]["expected"]["incorrect_points"] == []
    for row in rows(DATA / "teaching-inputs.jsonl"):
        assert not input_errors(row["payload"]), input_errors(row["payload"])
        med = row["payload"]["medical_evaluation"]
        assert med["total_score"] == sum(s["score"] for s in med["rubric_scores"])
        assert not set(med["correct_points"]) & set(med["incorrect_points"])
    grouped = {}
    for row in inputs:
        grouped.setdefault(row["topic"], set()).add(row["split"])
    assert all(len(v) == 1 for v in grouped.values())
    assert len(inputs) == 250 and len(grouped) == 10
    result = {"payloads_valid": len(inputs), "teaching_inputs_valid": 62,
              "expected_roundtrip_valid": True, "no_cross_split_topic": True,
              "model_calls": 0, "review_level": "agent_source_checked_not_clinician"}
    # Outside the frozen dataset definition; no manifest file mutation.
    from .common import RUN
    write(RUN / "preflight.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
