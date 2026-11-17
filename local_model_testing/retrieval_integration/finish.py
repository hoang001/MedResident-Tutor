"""Read-only final audit after the owned coordinator and model have exited."""

import json
import socket
import subprocess

from local_model_testing.experiment.control import controller_identity

from . import ledger
from .common import ROOT, RUN, digest, file_hash, read, system_snapshot, write
from .control import DOCKER, OWNER


def main():
    baseline = read(RUN / "baseline.json")
    rows = ledger.attempts()
    original = rows[: baseline["parent_attempts"]]
    added = rows[baseline["parent_attempts"] :]
    assert digest(original) == baseline["parent_rows_sha256"], "Old ledger rows changed"
    assert len(rows) <= 800 and len(added) <= 12
    assert all(r["category"] == "medical_retrieval_supplement" for r in added)
    assert all(r["status"] in {"completed", "failed"} for r in added), (
        "An attempt is not terminal; preserve it and inspect before closing"
    )
    changed = [
        name
        for name, sha in read(RUN / "protected-before.json").items()
        if not (ROOT / name).is_file() or file_hash(ROOT / name) != sha
    ]
    assert not changed, "Protected artifacts changed: " + ", ".join(changed)
    frozen = read(RUN / "experiment-manifest.json")
    frozen_changed = [
        name
        for name, sha in frozen["files"].items()
        if not (ROOT / name).is_file() or file_hash(ROOT / name) != sha
    ]
    if frozen_changed:
        archive = read(RUN / "frozen-inputs-archive.json")
        assert archive["original_manifest_sha256"] == file_hash(
            RUN / "experiment-manifest.json"
        )
        assert archive["files"] == frozen["files"]
        archive_root = (ROOT / archive["archive_root"]).resolve()
        assert archive_root.is_relative_to(RUN.resolve())
        assert all(
            file_hash(archive_root / name) == sha
            for name, sha in frozen["files"].items()
        )
        fix = read(RUN / "post-run-harness-fix.json")
        assert sorted(frozen_changed) == sorted(fix["changed_frozen_files"])
        assert all(
            file_hash(ROOT / name) == item["after_sha256"]
            for name, item in fix["changed_frozen_files"].items()
        )

    if OWNER.exists():
        owner = read(OWNER)
        current = controller_identity(owner["pid"])
        assert current is None or current["created"] != owner["created"], (
            "Owned coordinator still active"
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
    assert not owned, "Owned test/model container still running"
    assert not (RUN / "medical-container.cid").exists(), "Owned CID still present"
    for port in (8101, 8102):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0, "Model port still bound"

    service_names = [line.split()[0] for line in baseline["services"]]
    services = json.loads(subprocess.check_output([DOCKER, "inspect", *service_names]))
    service_ids = {c["Name"].lstrip("/"): c["Id"][:12] for c in services}
    for line in baseline["services"]:
        name, cid = line.split()
        assert service_ids[name] == cid, "An original web/DB container changed"
    assert all(c["State"]["Running"] for c in services)

    # Existing backend Python; no login, no model, no write, no Neo4j query.
    probe = """
import asyncio,json
from sqlalchemy import select,func
from app.core.config import get_settings
from app.core.database import SessionFactory,engine
from app.modules.questions.models import Question
from app.modules.progress.models import LearningResult
async def main():
 s=get_settings()
 async with SessionFactory() as db:
  leftovers=await db.scalar(select(func.count()).select_from(Question).where(Question.external_id.like('KGR_DEV_%')))
  learning=await db.scalar(select(func.count()).select_from(LearningResult))
 print(json.dumps(dict(provider=s.practice_provider,model_calls_enabled=s.model_calls_enabled,test_questions_remaining=leftovers,learning_results=learning)))
 await engine.dispose()
asyncio.run(main())
"""
    result = subprocess.run(
        [DOCKER, "exec", "-i", "medresident-tutor-backend-1", "python", "-"],
        input=probe.encode(),
        capture_output=True,
    )
    assert result.returncode == 0, "Read-only backend cleanup probe failed"
    backend = json.loads(result.stdout)
    assert backend["provider"] == baseline["runtime_audit"]["provider"]
    assert (
        backend["model_calls_enabled"]
        == baseline["runtime_audit"]["model_calls_enabled"]
    )
    assert backend["test_questions_remaining"] == 0
    preflight = read(RUN / "preflight.json")
    live = read(RUN / "live.json") if (RUN / "live.json").exists() else None
    for report in [preflight, *([live] if live else [])]:
        assert report.get("outer_transaction_rolled_back")
        assert report.get("test_attempts_and_questions_absent_after_rollback")
        assert report.get("mastery_unchanged")

    cleanup = {
        "owned_containers_running": [],
        "owned_coordinator_exited": True,
        "model_ports_closed": [8101, 8102],
        "original_services_same_ids_and_running": service_ids,
        "backend": backend,
        "original_ledger_rows_unchanged": True,
        "protected_file_count": len(read(RUN / "protected-before.json")),
        "protected_files_unchanged": True,
        "frozen_supplement_inputs_unchanged": not frozen_changed,
        "executed_frozen_inputs_preserved_and_verified": True,
        "post_run_harness_fixes": frozen_changed,
        "shared_ledger_total": len(rows),
        "supplement_attempts": len(added),
        "supplement_generations_started": sum(r["generation_started"] for r in added),
        "test_writes_rolled_back": True,
        "mastery_unchanged_in_test": True,
        "weights_adapters_cache_venv_kept": True,
        "autostart_enabled": False,
        "after_cleanup": system_snapshot(),
    }
    write(RUN / "cleanup.json", cleanup)
    print(
        json.dumps(
            {
                k: cleanup[k]
                for k in (
                    "shared_ledger_total",
                    "supplement_attempts",
                    "owned_coordinator_exited",
                    "model_ports_closed",
                    "protected_files_unchanged",
                    "original_ledger_rows_unchanged",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
