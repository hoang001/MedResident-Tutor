"""Offline regression checks. No model download, inference or test dataset access."""

import copy
import json
import unittest
from unittest.mock import patch

if __package__:
    from . import evaluate_baseline as baseline
    from .prepare_dataset import convert_sample
    from .validate_dataset import contract_errors, input_errors, prediction_metrics
else:
    import evaluate_baseline as baseline
    from prepare_dataset import convert_sample
    from validate_dataset import contract_errors, input_errors, prediction_metrics


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.inp = {
            "schema_version": "1.0.0", "question": "Question", "student_answer": "Answer",
            "medical_evaluation": {
                "correct_points": ["alpha beta gamma"], "incorrect_points": [],
                "missing_points": ["delta epsilon zeta"],
                "rubric_scores": [{"criterion_id": "C1", "criterion": "alpha beta gamma",
                                   "reason": "alpha beta gamma", "score": 1, "max_score": 1}],
                "total_score": 1, "max_score": 1, "sufficient_evidence": True, "evidence_refs": [],
            },
            "learner_context": {"mastery": [], "recurring_errors": [],
                                "recent_improvements": [], "recent_attempts_summary": None},
            "metadata": {"specialty": "demo", "course_group": None, "course_id": "C",
                         "course_name": "demo", "specialty_level": None, "topic_id": "T",
                         "topic_name": "demo", "concept_ids": []},
        }
        self.out = {
            "strengths": ["alpha beta gamma"], "corrections": [],
            "missing_focus": [{"missing_point": "delta epsilon zeta", "feedback": "delta epsilon zeta"}],
            "learning_priority": [{"focus": "delta epsilon zeta", "priority": "high", "reason": "Review"}],
            "feedback_text": "Review", "follow_up_question": None,
        }

    def test_valid_and_gold_roundtrip(self):
        self.assertFalse(input_errors(self.inp))
        metrics, errors = prediction_metrics(self.inp, self.out)
        self.assertFalse(errors)
        self.assertTrue(all(metrics.values()))
        original = copy.deepcopy(self.out)
        prepared = convert_sample({"sample_id": "demo", "input": self.inp, "gold_output": self.out})
        self.assertEqual(json.loads(prepared["messages"][2]["content"]), original)
        self.assertEqual(self.out, original)

    def test_strict_json_and_malformed_contract(self):
        for raw in ('```json\n{}\n```', '{"a":1,"a":2}', '{"a":NaN}'):
            _, metrics, _ = baseline.evaluate_prediction(self.inp, raw)
            self.assertFalse(metrics["json_valid"])
        for out in (None, [], {}, {**self.out, "strengths": [5]}):
            self.assertTrue(contract_errors(out))
            metrics, _ = prediction_metrics(self.inp, out)
            self.assertFalse(metrics["contract_valid"])

    def test_inconsistency_and_forbidden_scores(self):
        out = copy.deepcopy(self.out)
        out["missing_focus"].append(copy.deepcopy(out["missing_focus"][0]))
        out["corrections"] = [{"incorrect_point": "new claim", "feedback": "new claim"}]
        out["learning_priority"][0]["score"] = 4
        metrics, _ = prediction_metrics(self.inp, out)
        self.assertFalse(metrics["forbidden_score_fields"])
        out["learning_priority"][0].pop("score")
        metrics, _ = prediction_metrics(self.inp, out)
        self.assertFalse(metrics["corrections_consistency"])
        self.assertFalse(metrics["missing_focus_consistency"])
        self.assertFalse(metrics["medical_anchor_guard"])

    def test_evidence_and_context(self):
        self.inp["medical_evaluation"]["sufficient_evidence"] = False
        self.inp["learner_context"]["recurring_errors"] = [{"error_summary": "delta epsilon zeta"}]
        metrics, _ = prediction_metrics(self.inp, self.out)
        self.assertFalse(metrics["evidence_guard"])
        self.assertFalse(metrics["learner_context_usage"])
        self.out["feedback_text"] = "Chưa đủ căn cứ. Lỗi lặp lại."
        metrics, _ = prediction_metrics(self.inp, self.out)
        self.assertTrue(metrics["evidence_guard"])
        self.assertTrue(metrics["learner_context_usage"])

    def test_baseline_reads_only_validation(self):
        row = convert_sample({"sample_id": "TEACH_MED_0005_01_V01", "input": self.inp, "gold_output": self.out})
        rows = [{**row, "sample_id": f"TEACH_MED_0005_{i:02}_V01"} for i in range(1, 11)]
        with patch.object(baseline.rules, "read_jsonl", return_value=rows) as reader:
            self.assertEqual(len(baseline.load_validation()), 10)
            reader.assert_called_once_with(baseline.VALIDATION_FILE)
        rows[0]["sample_id"] = "TEACH_MED_0017_01_V01"
        with patch.object(baseline.rules, "read_jsonl", return_value=rows):
            with self.assertRaises(ValueError):
                baseline.load_validation()


if __name__ == "__main__":
    unittest.main()
