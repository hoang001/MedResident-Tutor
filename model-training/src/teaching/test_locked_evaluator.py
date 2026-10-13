"""Synthetic-only locked evaluator checks. Never open the test dataset."""

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
from unittest.mock import patch

if __package__:
    from . import evaluate_adapter_with_guards_test as locked
else:
    import evaluate_adapter_with_guards_test as locked


class LockedEvaluatorTests(unittest.TestCase):
    def rows(self):
        return [{"sample_id": f"synthetic-{i}", "messages": [
            {"role": "system", "content": "original system"},
            {"role": "user", "content": "{}"},
            {"role": "assistant", "content": "synthetic gold"},
        ]} for i in range(10)]

    def load(self, rows):
        with patch.object(locked.adapter.baseline.rules, "read_jsonl", return_value=rows) as read:
            with patch.object(locked.adapter.baseline, "input_errors", return_value=[]):
                result = locked.load_locked_test()
            read.assert_called_once_with(locked.TEST_FILE)
            return result

    def test_ten_unique_unchanged(self):
        rows = self.rows()
        before = copy.deepcopy(rows)
        self.assertIs(self.load(rows), rows)
        self.assertEqual(rows, before)

    def test_wrong_counts_fail_without_truncation(self):
        for rows in ([], self.rows()[:9], self.rows() + [self.rows()[0]]):
            with self.assertRaises(ValueError):
                self.load(rows)

    def test_duplicate_and_missing_ids_fail(self):
        rows = self.rows()
        rows[1]["sample_id"] = rows[0]["sample_id"]
        with self.assertRaises(ValueError):
            self.load(rows)
        rows[1]["sample_id"] = None
        with self.assertRaises(ValueError):
            self.load(rows)

    def test_bad_chat_fails(self):
        rows = self.rows()
        rows[0]["messages"][0]["role"] = "user"
        with self.assertRaises(ValueError):
            self.load(rows)

    def test_runner_identity_and_test_provenance(self):
        adapter = locked.adapter
        runner = locked.make_runner([])
        self.assertIs(runner.__code__, adapter.main.__code__)
        for key in ("MAX_NEW_TOKENS", "METRICS", "check_adapter", "ADAPTER_DIR", "summarize"):
            self.assertIs(runner.__globals__[key], adapter.main.__globals__[key])
        with patch.object(locked, "load_locked_test", return_value=self.rows()) as loader:
            runner.__globals__["load_validation"]()
            loader.assert_called_once_with()
        self.assertEqual(runner.__globals__["baseline"].VALIDATION_FILE, locked.TEST_FILE)
        self.assertNotEqual(adapter.baseline.VALIDATION_FILE, locked.TEST_FILE)
        self.assertEqual(runner.__globals__["OUTPUT_FILE"], locked.OUTPUT_FILE)
        with redirect_stdout(io.StringIO()) as output:
            runner.__globals__["print"]("=== TEACHING ADAPTER V1 SUMMARY ===")
        self.assertIn("=== TEACHING LOCKED TEST V1 + GUARDS SUMMARY ===", output.getvalue())


class MarkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.report = Path(self.directory.name) / "report.json"
        self.marker = Path(self.directory.name) / "run.started"
        for name, value in (("OUTPUT_FILE", self.report), ("RUN_MARKER", self.marker)):
            patcher = patch.object(locked, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_preflight_failure_no_marker(self):
        with patch.object(locked, "make_runner", return_value=lambda: (_ for _ in ()).throw(ValueError("preflight"))):
            with self.assertRaises(ValueError):
                locked.main()
        self.assertFalse(self.marker.exists())
        locked.ensure_unlocked()

    def test_marker_immediately_before_first_inference(self):
        calls = []
        def generate(*args, **kwargs):
            self.assertEqual(json.loads(self.marker.read_text())["status"], "STARTED")
            calls.append(1)
        model = locked.arm_inference(SimpleNamespace(generate=generate))
        self.assertFalse(self.marker.exists())
        model.generate()
        model.generate()
        self.assertEqual(len(calls), 2)

    def test_started_blocks(self):
        locked.start_run()
        with self.assertRaises(FileExistsError):
            locked.main()

    def test_completed_blocks(self):
        locked.start_run()
        locked.complete_run()
        with self.assertRaises(FileExistsError):
            locked.main()

    def test_successful_report_completed(self):
        def factory(records):
            def run():
                locked.start_run()
                records.extend({"prediction_before_guards": {}, "metrics_before_guards": {}} for _ in range(10))
                self.report.write_text(json.dumps({"cases": [{"prediction": {}, "metrics": {}, "errors": []} for _ in range(10)]}))
            return run
        with patch.object(locked, "make_runner", side_effect=factory):
            locked.main()
        self.assertEqual(json.loads(self.marker.read_text())["status"], "COMPLETED")
        self.assertTrue(json.loads(self.report.read_text())["locked_test"])

    def test_all_contexts_checked_before_marker(self):
        tokenizer = SimpleNamespace(apply_chat_template=lambda *a, **k: {"input_ids": SimpleNamespace(shape=(1, 2000))})
        model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=2048))
        with self.assertRaises(ValueError):
            locked.check_contexts(tokenizer, model, [{"messages": [{}, {}]}])
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
