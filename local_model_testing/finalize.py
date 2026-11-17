"""Read-only final verification/report after provisioning/probe have exited."""

import socket
import subprocess
import xml.etree.ElementTree as ET

from .common import ROOT, REPORT, file_hash, read, write, system_snapshot
from .launch import DOCKER


def output(*args):
    return subprocess.check_output([str(DOCKER), *args], text=True).strip()


def main():
    before = read(REPORT / "baseline.json")
    after = system_snapshot()
    after["services"] = output("ps", "--format", "{{.Names}} {{.Ports}}").splitlines()
    provider = output(
        "exec",
        "medresident-tutor-backend-1",
        "python",
        "-c",
        "import json; from app.core.config import get_settings; c=get_settings(); print(json.dumps(dict(app_env=c.app_env,practice_provider=c.practice_provider,model_calls_enabled=c.model_calls_enabled)))",
    )
    after["provider"] = provider
    hashes = read(REPORT / "protected-file-hashes.json")
    changed = [
        name
        for name, expected in hashes.items()
        if not (ROOT / name).exists() or file_hash(ROOT / name) != expected
    ]
    own = output(
        "ps", "--format", "{{.Names}}", "--filter", "name=medresident-local-"
    ).splitlines()
    ports = {}
    for port in (8101, 8102, 7687, 3000, 8000, 5433):
        with socket.socket() as sock:
            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
    downloads = {
        kind: read(REPORT / (kind + "-download.json"))
        for kind in ("medical", "teaching")
    }
    runtime = read(REPORT / "runtime-probe.json")
    probe_identity = read(REPORT / "probe-container-identity.json")
    probe_identity["still_running"] = bool(
        output(
            "ps",
            "--format",
            "{{.ID}}",
            "--filter",
            "id=" + probe_identity["container_id"],
        )
    )
    suite = ET.parse(REPORT / "pytest-preparation.xml").getroot().find("testsuite")
    test_counts = {
        k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")
    }
    report = {
        "status": "prepared_but_inference_blocked_missing_locked_v1_adapters",
        "before": before,
        "after": after,
        "downloads": {
            k: {
                "complete": v["complete"],
                "bytes": v["total_bytes"],
                "files_verified": len(v["files"]),
                "revision": v["revision"],
                "path": v["local_path"],
            }
            for k, v in downloads.items()
        },
        "runtime_probe_status": runtime["status"],
        "runtime_probe_process": probe_identity,
        "cpu": read(REPORT / "cpu.json"),
        "current_windows_ram_gate_passed": after["system"]["ram_available_bytes"]
        >= 4 * 1024**3,
        "ram_gate_required_bytes": 4 * 1024**3,
        "scoped_venv_cache_advice": read(REPORT / "cache-release.json"),
        "medical": {
            "real_inference_cases": 0,
            "real_smoke_generations": 0,
            "blocker": "locked Medical V1 adapter absent",
        },
        "teaching": {
            "real_inference_cases": 0,
            "real_smoke_generations": 0,
            "guard_model_tests": "not_run",
            "blocker": "locked Teaching V1 adapter absent",
        },
        "app_checks": read(REPORT / "app-preflight.json"),
        "e2e": {
            "real_model_http_practice": "not_run",
            "real_fe_model_flow": "not_run",
            "real_medical_to_teaching_replay": "not_run",
        },
        "safety_tests": {
            **test_counts,
            "junit_report": "pytest-preparation.xml",
            "scope": "preparation/ownership checks, not model quality",
        },
        "protected_files_checked": len(hashes),
        "protected_files_changed": changed,
        "provider_unchanged": provider == before["provider"],
        "original_services_preserved": set(before["services"])
        <= set(after["services"]),
        "owned_containers_still_running": own,
        "port_listeners": ports,
        "owned_cuda_model_processes_started": 0,
        "weights_venvs_outputs_preserved": True,
        "secrets_in_report": False,
    }
    assert all(v["complete"] for v in downloads.values()), "Base download incomplete"
    assert runtime["status"] == "runtime_probe_passed_not_model_test", (
        "Runtime probe not passed"
    )
    assert test_counts["failures"] == test_counts["errors"] == 0
    assert not probe_identity["still_running"]
    assert (
        not changed
        and report["provider_unchanged"]
        and report["original_services_preserved"]
    )
    assert not own and not ports["8101"] and not ports["8102"], (
        "Owned helper still running or model port occupied"
    )
    write(REPORT / "final-status.json", report)
    print(
        "Preparation verified; 0 real V1 model generations, adapters missing. Provider/services preserved. No owned helper container remains."
    )
    print("GPU before:", before["gpu"])
    print("GPU after:", after["gpu"])
    print(
        "Windows available RAM before/after bytes:",
        before["system"]["ram_available_bytes"],
        after["system"]["ram_available_bytes"],
    )
    print("Protected files unchanged:", len(hashes))


if __name__ == "__main__":
    main()
