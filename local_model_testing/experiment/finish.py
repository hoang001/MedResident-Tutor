"""Final integrity/ownership audit. Never stops unrelated services or changes data."""
import json
import socket

from .common import ROOT, RUN, file_hash, frozen, read, write
from .control import CID, OWNER, controller_identity, docker, protect
from .ledger import report
from local_model_testing.common import system_snapshot


def main():
    frozen()
    assert not CID.exists(), "Owned model worker still has an active CID"
    if OWNER.exists():
        owner = read(OWNER)
        live = controller_identity(owner["pid"])
        assert live is None or live["created"] != owner["created"], "Coordinator still running"
    containers = docker("ps", "--filter", "label=medresident.experiment="+RUN.name,
                        "--format", "{{.ID}}", capture_output=True, text=True).stdout.strip()
    assert not containers, "Owned experiment containers remain"
    protect()
    base = read(RUN / "baseline.json")
    current = docker("ps", "--format", "{{.Names}} {{.ID}}", capture_output=True, text=True).stdout.splitlines()
    for service in base["services"]:
        assert service in current, "An original service changed or stopped"
    attempts = report()
    assert len(attempts) <= 800
    assert len({(r["config"], r["sample_id"]) for r in attempts}) == len(attempts)
    assert not any(r["status"] == "started" for r in attempts), "Unreconciled interrupted attempt"
    parity = {}
    for kind in ("medical", "teaching"):
        a, b = [read(path) if path.exists() else {"status": "not_run"}
                for path in (RUN / (kind+"_"+name+"-process.json") for name in ("base", "adapter"))]
        if "metadata" not in a or "metadata" not in b:
            parity[kind] = {"evaluated": False, "reason": "A configuration did not load"}
            continue
        left, right = a["metadata"], b["metadata"]
        compared = ["base_model", "base_revision", "tokenizer_config_sha256", "chat_template_sha256",
                    "system_prompt_sha256", "generation", "quantization", "attention", "packages",
                    "dataset_manifest_sha256", "worker_code_sha256"]
        assert all(left[k] == right[k] for k in compared), "A/B control mismatch"
        assert left["adapter_enabled"] is False and right["adapter_enabled"] is True
        parity[kind] = {"evaluated": True, "matching_fields": compared,
                        "only_intervention": "attach supplied adapter"}
    ports = {}
    for port in (3000, 8000, 5433, 8101, 8102):
        with socket.socket() as sock:
            sock.settimeout(.5)
            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
    assert all(ports[str(p)] for p in (3000, 8000, 5433))
    assert not any(ports[str(p)] for p in (8101, 8102))
    result = {"owned_containers_exited": True, "coordinator_exited": True,
              "original_services_same_ids": True, "protected_files_unchanged": len(read(RUN/"protected-hashes.json")),
              "ports": ports, "attempts": len(attempts), "ab_parity": parity,
              "experiment_code_sha256": {str(p.relative_to(ROOT)): file_hash(p)
                  for p in sorted((ROOT/"local_model_testing/experiment").rglob("*.py"))},
              "after_cleanup": system_snapshot()}
    write(RUN / "cleanup-integrity.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "after_cleanup"}))


if __name__ == "__main__":
    main()
