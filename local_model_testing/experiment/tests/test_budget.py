import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from local_model_testing.experiment import ledger


def test_budget_persists_across_connections_and_counts_failed_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "RUN", tmp_path)
    monkeypatch.setattr(ledger, "DATA", tmp_path)
    (tmp_path / "experiment.json").write_text(json.dumps({"budgets": {"total": 3, "development": 2}}))
    first = ledger.reserve("base", "a", "development", "fp")
    ledger.generation_started(first)
    ledger.finish(first, "failed", "Deliberate fixture error")
    ledger.reserve("adapter", "b", "development", "fp2")
    with pytest.raises(RuntimeError, match="BUDGET"):
        ledger.reserve("base", "c", "development", "fp")
    assert len(ledger.report()) == 2 and ledger.report()[0]["generation_started"] == 1


def test_concurrent_duplicate_reservation_cannot_generate_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "RUN", tmp_path)
    monkeypatch.setattr(ledger, "DATA", tmp_path)
    (tmp_path / "experiment.json").write_text(json.dumps({"budgets": {"total": 10, "development": 10}}))
    ledger.connect().close()

    def reserve(_):
        try:
            return ledger.reserve("base", "same", "development", "fp")
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(reserve, range(3)))
    assert sum(r is not None for r in results) == 1
    assert len(ledger.report()) == 1
