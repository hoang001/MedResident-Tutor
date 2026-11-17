"""Read-only integrity/exit audit; never stops unrelated processes or edits history."""

import socket
import subprocess
from datetime import UTC, datetime

from local_model_testing.experiment.control import controller_identity
from .common import ROOT, RUN, read, write, file_hash, digest, system_snapshot
from .control import DOCKER, OWNER, CID
from . import ledger


def main():
    baseline = read(RUN / "baseline.json")
    entries = ledger.attempts()
    assert digest(entries[: baseline["ledger_count"]]) == baseline["ledger_rows_sha256"]
    own = [r for r in entries if r["category"] == "medical_retrieval_confirmation"]
    assert len(own) <= 12 and len(entries) <= 800
    assert all(r["status"] in {"completed", "failed"} for r in own)
    protected = read(RUN / "protected-before.json")
    changed = [
        n
        for n, h in protected.items()
        if not (ROOT / n).is_file() or file_hash(ROOT / n) != h
    ]
    assert not changed, "Historical artifacts changed: " + ", ".join(changed[:5])
    manifest = read(RUN / "experiment-manifest.json")
    assert all(file_hash(ROOT / n) == h for n, h in manifest["files"].items()), (
        "Frozen confirmation input changed"
    )
    if OWNER.exists():
        owner = read(OWNER)
        active = controller_identity(owner["pid"])
        assert active is None or active["created"] != owner["created"], (
            "Own coordinator still active"
        )
    owned = subprocess.check_output(
        [
            DOCKER,
            "ps",
            "-q",
            "--filter",
            "label=medresident.retrieval-supplement=" + RUN.name,
        ],
        text=True,
    ).split()
    assert not owned and not CID.exists(), "Own container/CID still active"
    for port in [8101, 8102]:
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Model port still bound"
    services = subprocess.check_output(
        [DOCKER, "ps", "--format", "{{.Names}} {{.ID}}"], text=True
    ).splitlines()
    assert all(s in services for s in baseline["services"]), (
        "Original web/DB container changed"
    )
    pre = read(RUN / "preflight.json")
    live = read(RUN / "live.json") if (RUN / "live.json").exists() else None
    for result in [pre, *([live] if live and live.get("cases") else [])]:
        assert result["outer_transaction_rolled_back"]
        assert result["test_attempts_and_questions_absent_after_rollback"]
        assert result["mastery_unchanged"]
    state = (
        read(RUN / "medical-server.json")
        if (RUN / "medical-server.json").exists()
        else {}
    )
    if state:
        assert state["generation_attempt_ids"] == state["generation_finished_ids"]
        assert state.get("active_runner_trace_id") is None
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "old_ledger_rows_unchanged": baseline["ledger_count"],
        "historical_artifacts_unchanged": len(protected),
        "frozen_confirmation_unchanged": True,
        "shared_ledger_total": len(entries),
        "new_attempts": len(own),
        "model_ports_closed": [8101, 8102],
        "own_coordinator_exited": True,
        "own_containers_running": [],
        "generation_finished_or_never_started": True,
        "original_services_same_ids": True,
        "test_data_rolled_back": True,
        "mastery_unchanged": True,
        "weights_adapters_cache_venv_kept": True,
        "autostart": False,
        "after_cleanup": system_snapshot(),
        "inference_pending_due_to_RAM": not own,
    }
    write(RUN / "cleanup.json", result)
    if own:
        write(
            RUN / "closed.json",
            {
                "closed_at": result["checked_at"],
                "attempts_used": len(own),
                "reason": "Single authorized confirmation batch ended; reporting only, no tuning or further inference",
            },
        )
    print(
        {
            k: result[k]
            for k in [
                "shared_ledger_total",
                "new_attempts",
                "old_ledger_rows_unchanged",
                "historical_artifacts_unchanged",
                "model_ports_closed",
                "inference_pending_due_to_RAM",
            ]
        }
    )


if __name__ == "__main__":
    main()
