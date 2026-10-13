"""Synthetic offline tests; no dataset or model access."""

import copy
import unittest

if __package__:
    from .apply_teaching_guards import apply_teaching_guards, match_point, CAUTION
    from . import evaluate_adapter_with_guards as evaluator
else:
    from apply_teaching_guards import apply_teaching_guards, match_point, CAUTION
    import evaluate_adapter_with_guards as evaluator


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.good = "Trình bày đầy đủ nội dung tiêu chí alpha."
        self.issue = "Giải thích nội dung tiêu chí beta còn thiếu."
        self.other = "Trình bày nội dung tiêu chí gamma còn thiếu."
        self.payload = {"medical_evaluation": {
            "correct_points": [self.good], "incorrect_points": [],
            "missing_points": [self.issue, self.other], "sufficient_evidence": True,
        }, "learner_context": {"recurring_errors": [], "recent_improvements": []}}
        self.out = {"strengths": [self.good], "corrections": [], "missing_focus": [],
                    "learning_priority": [{"focus": self.other, "priority": "high", "reason": "Review"},
                                          {"focus": self.issue, "priority": "medium", "reason": "Review"}],
                    "feedback_text": "Feedback", "follow_up_question": "Question", "score": 5}

    def test_evidence_false(self):
        self.payload["medical_evaluation"]["sufficient_evidence"] = False
        result = apply_teaching_guards(self.payload, self.out)
        self.assertEqual(result["feedback_text"], "Feedback " + CAUTION)

    def test_recurring_match(self):
        self.payload["learner_context"]["recurring_errors"] = [{"error_summary": "Lỗi trước đây: " + self.issue}]
        result = apply_teaching_guards(self.payload, self.out)
        self.assertEqual(result["learning_priority"][0]["focus"], self.issue)
        self.assertEqual(result["learning_priority"][0]["priority"], "high")
        self.assertIn("lặp lại gần đây", result["learning_priority"][0]["reason"])
        self.assertEqual(len(result["learning_priority"]), 2)
        self.out["learning_priority"] = []
        self.assertEqual(apply_teaching_guards(self.payload, self.out)["learning_priority"], [])

    def test_improvement_match(self):
        self.payload["learner_context"]["recent_improvements"] = [{"improvement_summary": "Đã cải thiện: " + self.good}]
        result = apply_teaching_guards(self.payload, self.out)
        self.assertIn("Bạn đã cải thiện ở nội dung: " + self.good, result["feedback_text"])

    def test_no_match_unchanged(self):
        self.payload["learner_context"] = {"recurring_errors": [{"error_summary": "Nội dung hoàn toàn khác"}],
                                          "recent_improvements": [{"improvement_summary": "Ý không liên quan"}]}
        self.assertEqual(apply_teaching_guards(self.payload, self.out), self.out)

    def test_idempotent_and_protected(self):
        self.payload["medical_evaluation"]["sufficient_evidence"] = False
        self.payload["learner_context"] = {"recurring_errors": [{"error_summary": self.issue}],
                                          "recent_improvements": [{"improvement_summary": self.good}]}
        original, payload = copy.deepcopy(self.out), copy.deepcopy(self.payload)
        result = apply_teaching_guards(self.payload, self.out)
        self.assertEqual(apply_teaching_guards(self.payload, result), result)
        for key in original:
            if key not in {"learning_priority", "feedback_text"}:
                self.assertEqual(result[key], original[key])
        self.assertEqual(self.out, original)
        self.assertEqual(self.payload, payload)

    def test_ambiguous_and_negation_rejected(self):
        self.assertIsNone(match_point(self.issue + " " + self.other, [self.issue, self.other]))
        self.assertIsNone(match_point("không " + self.issue, [self.issue]))
        # Changed negation in fuzzy comparison must not be accepted.
        self.assertIsNone(match_point("không giải thích đầy đủ nội dung tiêu chí beta còn thiếu", [self.issue]))

    def test_runner_reuses_original_loader_and_generation(self):
        runner = evaluator.make_runner([])
        adapter = evaluator.adapter
        self.assertIs(runner.__code__, adapter.main.__code__)
        for key in ("load_validation", "MAX_NEW_TOKENS", "METRICS", "check_adapter", "baseline", "summarize"):
            self.assertIs(runner.__globals__[key], adapter.main.__globals__[key])


if __name__ == "__main__":
    unittest.main()
