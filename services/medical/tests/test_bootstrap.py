"""Deployment preflight and shell startup, using tiny synthetic artifacts only."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from medical_service import bootstrap

ROOT = Path(__file__).resolve().parents[3]
KEY = "synthetic-service-key-only"


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_SERVICE_API_KEY", KEY)
    monkeypatch.setenv("MEDICAL_API_KEY", "short-legacy-key")
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    paths = {}
    for prefix, model_id, model_type in (
        ("MEDICAL", "Qwen/Qwen3-4B-Instruct-2507", "qwen3"),
        ("TEACHING", "Qwen/Qwen2.5-7B-Instruct", "qwen2"),
    ):
        base, adapter = tmp_path / (prefix + " base"), tmp_path / (prefix + " adapter")
        base.mkdir()
        adapter.mkdir()
        (base / "config.json").write_text(json.dumps({"model_type": model_type}))
        (base / "tokenizer_config.json").write_text("{}")
        (base / "model.safetensors").write_bytes(b"synthetic base only")
        (adapter / "adapter_model.safetensors").write_bytes(b"synthetic adapter " + prefix.encode())
        (adapter / "adapter_config.json").write_text(
            json.dumps(
                {
                    "base_model_name_or_path": model_id,
                    "peft_type": "LORA",
                    "task_type": "CAUSAL_LM",
                }
            )
        )
        monkeypatch.setenv(prefix + "_BASE_MODEL_PATH", str(base))
        monkeypatch.setenv(prefix + "_ADAPTER_PATH", str(adapter))
        paths[prefix] = (base, adapter)
    hashes = bootstrap.deployment_hashes()
    for name, value in hashes.items():
        monkeypatch.setenv(name, value)
    return paths, hashes


def test_hash_inventory_requires_no_secret_or_gpu(deployment, monkeypatch, capsys):
    _, expected = deployment
    monkeypatch.delenv("MODEL_SERVICE_API_KEY")
    monkeypatch.delenv("MEDICAL_API_KEY")
    assert bootstrap.main(["--print-hashes"]) == 0
    output = capsys.readouterr().out
    assert dict(line.split("=", 1) for line in output.splitlines()) == expected
    assert len(expected) == 6


def test_check_only_verifies_both_without_loading_or_exec(deployment, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("GPU load/exec is forbidden in preflight")

    monkeypatch.setattr(bootstrap.TeachingRunner, "load", forbidden)
    monkeypatch.setattr(bootstrap.os, "execv", forbidden)
    monkeypatch.setattr(bootstrap, "ensure_port_available", forbidden)
    assert bootstrap.main(["--check-only"]) == 0
    output = capsys.readouterr().out
    rows = [json.loads(line) for line in output.splitlines()]
    assert [row["stage"] for row in rows] == ["MEDICAL", "TEACHING"]
    assert all(row["status"] == "ARTIFACTS_VERIFIED" for row in rows)
    assert KEY not in output


@pytest.mark.parametrize("stage", ["MEDICAL", "TEACHING"])
def test_changed_weights_fail_before_gpu_start(deployment, monkeypatch, capsys, stage):
    paths, _ = deployment
    (paths[stage][1] / "adapter_model.safetensors").write_bytes(b"changed")
    invoked = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda *args: invoked.append(args))
    assert bootstrap.main(["--check-only"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.err)["error"]["code"] == stage + "_ADAPTER_HASH_MISMATCH"
    assert KEY not in output.out + output.err and not invoked


def test_missing_teaching_hash_is_calculated_locally(deployment, monkeypatch, capsys):
    _, hashes = deployment
    monkeypatch.delenv("TEACHING_ADAPTER_SHA256")
    assert bootstrap.main(["--check-only"]) == 0
    assert os.environ["TEACHING_ADAPTER_SHA256"] == hashes["TEACHING_ADAPTER_SHA256"]
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[-1]["hash_mode"] == "computed"


def test_api_key_and_artifacts_are_enough_without_six_manual_hashes(
    deployment, monkeypatch, capsys
):
    _, hashes = deployment
    for name in hashes:
        monkeypatch.delenv(name)
    assert bootstrap.main(["--check-only"]) == 0
    assert all(os.environ[name] == expected for name, expected in hashes.items())
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row["hash_mode"] for row in rows] == ["computed", "computed"]


def test_start_execs_one_server_and_reuses_legacy_key(deployment, monkeypatch, capsys):
    monkeypatch.delenv("MODEL_SERVICE_API_KEY")
    monkeypatch.setenv("MEDICAL_API_KEY", KEY)
    monkeypatch.setattr(bootstrap, "ensure_port_available", lambda: None)
    invoked = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda *args: invoked.append(args))
    assert bootstrap.main([]) == 0
    assert invoked == [
        (
            sys.executable,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "medical_service.unified:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--workers",
                "1",
                "--no-access-log",
            ],
        )
    ]
    assert KEY not in capsys.readouterr().out


def test_placeholder_model_key_never_uses_legacy_fallback(deployment, monkeypatch, capsys):
    monkeypatch.setenv("MODEL_SERVICE_API_KEY", "<REPLACE_WITH_REAL_KEY>")
    monkeypatch.setenv("MEDICAL_API_KEY", KEY)
    assert bootstrap.main(["--check-only"]) == 1
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "MEDICAL_CONFIGURATION_INVALID"


def test_bad_preflight_never_stops_existing_service(deployment, monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("TEACHING_ADAPTER_SHA256", "0" * 64)
    monkeypatch.setattr(bootstrap, "ensure_port_available", lambda: calls.append("stop"))
    assert bootstrap.main([]) == 1
    output = capsys.readouterr()
    assert json.loads(output.err)["error"]["code"] == "TEACHING_ADAPTER_HASH_MISMATCH"
    assert calls == []


@pytest.mark.parametrize("legacy_key", [False, True])
def test_main_entrypoint_uses_one_unified_app_and_both_configs(deployment, monkeypatch, legacy_key):
    if legacy_key:
        monkeypatch.delenv("MODEL_SERVICE_API_KEY")
        monkeypatch.setenv("MEDICAL_API_KEY", KEY)
    captured = []
    marker = object()

    def factory(settings, **kwargs):
        captured.append((settings, kwargs))
        return marker

    monkeypatch.setattr("medical_service.app.create_app", factory)
    for name in ("medical_service.unified", "medical_service.main"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    main = importlib.import_module("medical_service.main")
    unified = importlib.import_module("medical_service.unified")
    assert main.app is unified.app is marker
    assert len(captured) == 1
    settings, kwargs = captured[0]
    assert kwargs["require_teaching"] is True
    assert settings.api_key == kwargs["teaching_settings"].api_key == KEY


def test_shell_loads_env_sets_paths_and_appends_log_without_printing_key(tmp_path):
    fake = tmp_path / "fake python"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'test "$HF_HUB_OFFLINE" = 1 && test "$TRANSFORMERS_OFFLINE" = 1 || exit 3\n'
        'test "$WEB_CONCURRENCY" = 1 || exit 4\n'
        'test "$MEDICAL_BASE_MODEL_PATH" = /workspace/models/qwen3-4b-instruct-2507 || exit 5\n'
        'test "$TEACHING_BASE_MODEL_PATH" = /workspace/models/qwen2.5-7b-instruct || exit 6\n'
        'test "$MEDICAL_ADAPTER_PATH" = /workspace/adapters/medical-v1 || exit 7\n'
        'test "$TEACHING_ADAPTER_PATH" = /workspace/adapters/teaching-v1 || exit 8\n'
        'test -n "$MODEL_SERVICE_API_KEY" && test -n "$PYTHONPATH" || exit 9\n'
        "printf '%s\\n' \"$@\"\n"
    )
    fake.chmod(0o700)
    envfile = tmp_path / "private env"
    envfile.write_text("MODEL_SERVICE_API_KEY='" + KEY + "'\n")
    logfile = tmp_path / "outputs" / "model-service.log"
    logfile.parent.mkdir()
    logfile.write_text("previous log\n")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("MEDICAL_", "TEACHING_", "MODEL_SERVICE_"))
    }
    env.update(
        MODEL_SERVICE_ENV_FILE=str(envfile),
        MODEL_SERVICE_PYTHON=str(fake),
        MODEL_SERVICE_LOG_FILE=str(logfile),
    )
    result = subprocess.run(
        ["bash", "-x", str(ROOT / "services/medical/start-runpod.sh"), "--check-only"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "medical_service.bootstrap\n--check-only" in result.stdout
    log = logfile.read_text()
    assert log.startswith("previous log\n") and "medical_service.bootstrap" in log
    assert KEY not in result.stdout + result.stderr + log


def test_explicit_environment_key_wins_over_secret_file(tmp_path):
    fake = tmp_path / "fake-python"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'test "$MODEL_SERVICE_API_KEY" = "$EXPECTED_KEY" || exit 8\n'
        "echo KEY_PRECEDENCE_OK\n"
    )
    fake.chmod(0o700)
    envfile = tmp_path / "service.env"
    envfile.write_text("MODEL_SERVICE_API_KEY='file-secret-key-only'\n")
    explicit_key = "explicit-secret-key-only"
    env = {k: v for k, v in os.environ.items() if not k.startswith("MODEL_SERVICE_")}
    env.update(
        MODEL_SERVICE_ENV_FILE=str(envfile),
        MODEL_SERVICE_PYTHON=str(fake),
        MODEL_SERVICE_API_KEY=explicit_key,
        EXPECTED_KEY=explicit_key,
        MODEL_SERVICE_LOG_FILE=str(tmp_path / "service.log"),
    )
    result = subprocess.run(
        ["bash", "-x", str(ROOT / "scripts/runpod/start_model_service.sh"), "--check-only"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "KEY_PRECEDENCE_OK" in result.stdout
    assert explicit_key not in result.stdout + result.stderr
    assert "file-secret-key-only" not in result.stdout + result.stderr
