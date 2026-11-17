"""Preparation/safety tests only. No locked benchmark and no model generation."""

import json
import subprocess
import sys

import pytest

from local_model_testing import artifacts, launch
from local_model_testing.common import ROOT, REPORT, file_hash, read


def test_frozen_new_cases_and_gold_separation():
    manifest = read(REPORT / "integration-inputs.json")
    assert len(manifest["cases"]) == 10
    for case in manifest["cases"]:
        path = REPORT / "inputs" / (case["case_id"] + ".json")
        expected_path = REPORT / "expected" / (case["case_id"] + ".json")
        assert file_hash(path) == case["input_sha256"]
        assert file_hash(expected_path) == case["expected_sha256"]
        payload, expected = read(path), read(expected_path)
        assert set(payload) == {"question", "student_answer", "rubric", "evidence"}
        if case["label"] == "empty":
            assert payload["student_answer"] == "" and expected["app_http"] == 422
            assert expected["model_call"] is False
        else:
            assert (
                sum(c["score"] for c in expected["criteria"]) == expected["total_score"]
            )
            assert {e for c in expected["criteria"] for e in c["evidence_refs"]} <= {
                e["source_unit_id"] for e in payload["evidence"]
            }


def test_missing_adapter_fails_before_gpu_import(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "MODELS", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    before = "torch" in sys.modules
    with pytest.raises(FileNotFoundError, match="MEDICAL_V1_ADAPTER_MISSING"):
        artifacts.check("medical")
    assert ("torch" in sys.modules) == before


def test_wrong_adapter_never_falls_back_to_base(tmp_path, monkeypatch):
    adapter = tmp_path / "model-training/outputs/teaching-qwen2.5-v1/adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": "wrong/model",
                "peft_type": "LORA",
                "task_type": "CAUSAL_LM",
            }
        )
    )
    (adapter / "adapter_model.safetensors").write_bytes(b"deliberately-not-real-model")
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "MODELS", tmp_path)
    with pytest.raises(ValueError, match="ADAPTER_IDENTITY_MISMATCH"):
        artifacts.check("teaching")


def test_host_ram_gate_stops_before_container_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, "CID", tmp_path / "no-container.cid")
    monkeypatch.setattr(launch, "REPORT", tmp_path)
    monkeypatch.setattr(launch, "check", lambda kind: None)
    monkeypatch.setattr(
        launch,
        "system_snapshot",
        lambda: {"system": {"ram_available_bytes": 3 * 1024**3}},
    )
    monkeypatch.setattr(
        launch.subprocess,
        "Popen",
        lambda *a, **k: pytest.fail("Must not launch while host RAM is insufficient"),
    )
    with pytest.raises(RuntimeError, match="WINDOWS_AVAILABLE_RAM_BELOW_4_GIB"):
        launch.start("medical", False)


def test_stop_ignores_reused_pid_or_wrong_identity(tmp_path, monkeypatch):
    from local_model_testing import process_control

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "pid": 12345,
                "created": 1,
                "executable": "expected.exe",
                "module": "local_model_testing.worker",
            }
        )
    )

    class OtherProcess:
        def create_time(self):
            return 2

        def terminate(self):
            pytest.fail("Must never terminate a different/reused PID")

    monkeypatch.setattr(process_control, "STATE", state)
    monkeypatch.setattr(process_control.psutil, "Process", lambda _pid: OtherProcess())
    with pytest.raises(RuntimeError, match="PID_IDENTITY_MISMATCH"):
        process_control.stop()
    assert state.exists()


def test_real_docker_stop_checks_ownership(tmp_path, monkeypatch):
    # Two disposable CPU containers created by this test, never user containers.
    monkeypatch.setattr(launch, "CID", tmp_path / "worker.cid")
    monkeypatch.setattr(launch, "REPORT", tmp_path)
    created = []

    def make(labels):
        cmd = [str(launch.DOCKER), "run", "--rm", "-d", "--entrypoint", "python"]
        for label in labels:
            cmd += ["--label", label]
        cmd += [launch.IMAGE, "-c", "import time; time.sleep(300)"]
        cid = subprocess.check_output(cmd, text=True).strip()
        created.append(cid)
        launch.CID.write_text(cid)
        return cid

    try:
        foreign = make([])
        with pytest.raises(ValueError, match="CONTAINER_OWNERSHIP_MISMATCH"):
            launch.stop()
        assert launch.CID.exists()
        assert (
            subprocess.check_output(
                [
                    str(launch.DOCKER),
                    "inspect",
                    "--format",
                    "{{.State.Running}}",
                    foreign,
                ],
                text=True,
            ).strip()
            == "true"
        )
        make(["medresident.local-model-test=1", "medresident.project=" + str(ROOT)])
        launch.stop()
        assert not launch.CID.exists()
        assert (
            read(tmp_path / "container-stop.json")["status"]
            == "stopped_owned_container"
        )
    finally:
        for cid in created:
            subprocess.run(
                [str(launch.DOCKER), "rm", "-f", cid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
