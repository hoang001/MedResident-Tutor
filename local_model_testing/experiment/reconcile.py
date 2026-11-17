"""Record interrupted attempts after verified worker exit; never retry or alter outputs."""
import json
import shutil
from datetime import UTC, datetime

from . import ledger
from .common import DATA, RUN, fingerprint, frozen, read, rows, write
from .control import CID, OWNER, controller_identity, docker


def main():
    frozen()
    assert not CID.exists(), "Verify owned worker exit using control.stop first"
    if OWNER.exists():
        owner = read(OWNER)
        live = controller_identity(owner["pid"])
        assert live is None or live["created"] != owner["created"], "Coordinator still active"
    assert not docker("ps", "--filter", "label=medresident.experiment="+RUN.name,
                      "--format", "{{.ID}}", capture_output=True, text=True).stdout.strip()
    orphans = [r for r in ledger.report() if r["status"] == "started"]
    event = {"recorded_at": datetime.now(UTC).isoformat(),
             "original_docker_errors": ["error waiting for container: unexpected EOF",
                                        "Docker Desktop is unable to start"],
             "cause": "Docker/WSL engine exited; root cause not independently established",
             "recovery": "Docker Desktop normal restart; original web/BE/PG containers started with same IDs",
             "automatic_model_retry": False, "interrupted_attempts": []}
    for attempt in orphans:
        config = attempt["config"]
        archive = RUN/"segments"/config/("interrupted-attempt-"+str(attempt["id"]))
        assert not archive.exists(), "Archive exists; refusing overwrite"
        archive.mkdir(parents=True)
        for suffix in ("-process.json", "-host-memory.json"):
            source = RUN/(config+suffix)
            if source.exists():
                shutil.copy2(source, archive/source.name)
        row = next(r for r in rows(DATA/(config.split("_")[0]+"-inputs.jsonl"))
                   if r["sample_id"] == attempt["sample_id"])
        error = {"type": "interrupted", "code": "DOCKER_ENGINE_EXITED",
                 "message": "error waiting for container: unexpected EOF; Docker Desktop is unable to start",
                 "retry": False}
        path = RUN/config/(attempt["sample_id"]+".json")
        assert not path.exists(), "Checkpoint already exists; inspect instead of overwriting"
        write(path, {"sample_id": attempt["sample_id"], "attempt_id": attempt["id"],
                     "fingerprint": attempt["fingerprint"],
                     "payload_sha256": fingerprint(row["payload"]), "split": row["split"],
                     "generation_started": bool(attempt["generation_started"]),
                     "schema_valid": False, "contract_valid": False, "error": error,
                     "reconciliation": "No raw response returned; interrupted attempt remains in denominator"})
        ledger.finish(attempt["id"], "interrupted", json.dumps(error))
        event["interrupted_attempts"].append(attempt)
    if orphans:
        target = RUN/("runtime-interruption-"+str(orphans[0]["id"])+".json")
        assert not target.exists()
        write(target, event)
    print(json.dumps({"interrupted_without_retry": len(orphans)}))


if __name__ == "__main__":
    main()
