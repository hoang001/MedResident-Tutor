import json

import pytest

from local_model_testing.experiment import control


def test_stop_refuses_reused_pid_before_termination(tmp_path, monkeypatch):
    owner = tmp_path / "owner.json"
    owner.write_text(json.dumps({"pid": 123, "created": "original"}))
    monkeypatch.setattr(control, "OWNER", owner)
    monkeypatch.setattr(control, "STOP_REQUEST", tmp_path / "stop.json")
    monkeypatch.setattr(control, "controller_identity", lambda pid: {
        "pid": pid, "created": "original", "command": "unrelated service"})

    def forbidden(*args, **kwargs):
        pytest.fail("Must not terminate a process whose identity differs")

    monkeypatch.setattr(control.subprocess, "run", forbidden)
    with pytest.raises(RuntimeError, match="ownership mismatch"):
        control.request_stop()


def test_stop_without_owned_cid_never_calls_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "CID", tmp_path / "absent.cid")

    def forbidden(*args, **kwargs):
        pytest.fail("No owned CID means no Docker/process stop")

    monkeypatch.setattr(control, "docker", forbidden)
    control.stop()


def test_reused_pid_is_skipped_without_killing_new_owner(tmp_path, monkeypatch):
    owner = tmp_path / "owner.json"
    owner.write_text(json.dumps({"pid": 123, "created": "old"}))
    monkeypatch.setattr(control, "OWNER", owner)
    monkeypatch.setattr(control, "CID", tmp_path / "absent.cid")
    monkeypatch.setattr(control, "STOP_REQUEST", tmp_path / "stop.json")
    monkeypatch.setattr(control, "controller_identity", lambda pid: {
        "pid": pid, "created": "new", "command": "unrelated"})
    monkeypatch.setattr(control.subprocess, "run", lambda *a, **k: pytest.fail("Reused PID must survive"))
    control.request_stop()


def test_completed_resume_does_not_reload_or_rewrite_original_wall_time(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "RUN", tmp_path)
    monkeypatch.setattr(control, "OWNER", tmp_path/"absent-owner.json")
    monkeypatch.setattr(control, "CID", tmp_path/"absent.cid")
    monkeypatch.setattr(control, "frozen", lambda: None)
    for name in control.CONFIGS:
        (tmp_path/(name+"-process.json")).write_text(json.dumps({"status": "finished"}))
    monkeypatch.setattr(control, "write", lambda *a: pytest.fail("Do not rewrite run metadata"))
    monkeypatch.setattr(control, "system_snapshot", lambda: pytest.fail("No model/hardware load"))
    control.run("all")
