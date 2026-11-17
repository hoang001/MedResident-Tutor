import json
from types import SimpleNamespace

import pytest

from local_model_testing.experiment import reconcile


def test_interruption_is_terminal_without_reserving_or_retrying(tmp_path, monkeypatch):
    monkeypatch.setattr(reconcile, "RUN", tmp_path)
    monkeypatch.setattr(reconcile, "DATA", tmp_path)
    monkeypatch.setattr(reconcile, "CID", tmp_path/"absent.cid")
    monkeypatch.setattr(reconcile, "OWNER", tmp_path/"absent-owner.json")
    monkeypatch.setattr(reconcile, "frozen", lambda: None)
    monkeypatch.setattr(reconcile, "docker", lambda *a, **k: SimpleNamespace(stdout=""))
    (tmp_path/"medical-inputs.jsonl").write_text(json.dumps({"sample_id": "S",
        "split": "test", "payload": {"student_answer": "example"}})+"\n")
    original = {"status": "running", "config": "medical_adapter"}
    (tmp_path/"medical_adapter-process.json").write_text(json.dumps(original))
    attempt = {"status": "started", "id": 1, "config": "medical_adapter",
               "sample_id": "S", "generation_started": 1, "fingerprint": "frozen"}
    monkeypatch.setattr(reconcile.ledger, "report", lambda: [attempt])
    monkeypatch.setattr(reconcile.ledger, "reserve", lambda *a: pytest.fail("No new attempt"))

    def finish(ident, status, reason):
        assert ident == 1
        attempt["status"] = status
        attempt["reason"] = reason

    monkeypatch.setattr(reconcile.ledger, "finish", finish)
    reconcile.main()
    output = reconcile.read(tmp_path/"medical_adapter/S.json")
    assert output["error"]["code"] == "DOCKER_ENGINE_EXITED"
    assert not output["error"]["retry"] and output["generation_started"]
    assert attempt["status"] == "interrupted"
    assert reconcile.read(tmp_path/"segments/medical_adapter/interrupted-attempt-1/medical_adapter-process.json") == original
    reconcile.main()  # No still-started attempt, therefore no rewrite or inference.
    assert len(list((tmp_path/"segments/medical_adapter").iterdir())) == 1


def test_reconciliation_refuses_active_controller(tmp_path, monkeypatch):
    monkeypatch.setattr(reconcile, "CID", tmp_path/"absent.cid")
    owner = tmp_path/"owner.json"
    owner.write_text(json.dumps({"pid": 7, "created": "same"}))
    monkeypatch.setattr(reconcile, "OWNER", owner)
    monkeypatch.setattr(reconcile, "frozen", lambda: None)
    monkeypatch.setattr(reconcile, "controller_identity", lambda pid: {"created": "same"})
    with pytest.raises(AssertionError, match="Coordinator still active"):
        reconcile.main()
