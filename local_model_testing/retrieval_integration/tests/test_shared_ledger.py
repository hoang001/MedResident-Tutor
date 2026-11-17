import json
import sqlite3

import pytest

from local_model_testing.retrieval_integration import ledger


def isolated(tmp_path, monkeypatch, total=532):
    path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE attempts(id INTEGER PRIMARY KEY,config TEXT,sample_id TEXT,category TEXT,"
            "fingerprint TEXT,started TEXT,finished TEXT,status TEXT,generation_started INTEGER DEFAULT 0,reason TEXT)"
        )
        db.executemany(
            "INSERT INTO attempts(config,sample_id,category,status) VALUES('old',?,'medical_final','completed')",
            [(str(i),) for i in range(total)],
        )

    def connection():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        return db

    monkeypatch.setattr(ledger, "connection", connection)
    monkeypatch.setattr(ledger, "RUN", tmp_path)
    (tmp_path / "authorization.json").write_text(
        json.dumps({"shared_total_ceiling": 800, "supplement_max_attempts": 12})
    )
    return path


def test_supplement_appends_to_existing_budget_and_preserves_old_rows(
    tmp_path, monkeypatch
):
    isolated(tmp_path, monkeypatch)
    before = ledger.attempts()
    for mode in ("vector", "hybrid"):
        for i in range(6):
            ledger.reserve("retrieval_medical_" + mode + "_v1", str(i), "F")
    assert len(ledger.attempts()) == 544 and ledger.attempts()[:532] == before
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        ledger.reserve("retrieval_medical_vector_v1", "extra", "F")


def test_shared_ceiling_is_not_reset_by_supplement(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch, total=799)
    ledger.reserve("retrieval_medical_vector_v1", "one", "F")
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        ledger.reserve("retrieval_medical_hybrid_v1", "two", "F")


def test_generation_cannot_run_twice_or_retry_wrong_output(tmp_path, monkeypatch):
    isolated(tmp_path, monkeypatch)
    ident = ledger.reserve("retrieval_medical_vector_v1", "one", "F")
    ledger.started(ident)
    with pytest.raises(RuntimeError, match="DUPLICATE_OR_UNAUTHORIZED"):
        ledger.started(ident)
    ledger.finish(ident, "failed", {"code": "MODEL_OUTPUT_TOTAL_MISMATCH"})
    with pytest.raises(RuntimeError, match="NO_RETRY"):
        ledger.reserve("retrieval_medical_vector_v1", "one", "F")
