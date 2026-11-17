"""Create a new authorized run and protect all earlier experiment artifacts."""

import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime

from .common import (
    ROOT,
    RUN,
    PARENT,
    CORPUS,
    ENCODER,
    digest,
    file_hash,
    write,
    system_snapshot,
)
from .control import DOCKER
from . import ledger

OLD = ROOT / "data/evaluation/runs/retrieval-integration-20261111"


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    if (RUN / "baseline.json").exists():
        print("Existing confirmation baseline retained; no new authorization or reset")
        return
    previous = ledger.attempts()
    assert len(previous) + 12 <= 800
    assert not any(r["category"] == "medical_retrieval_confirmation" for r in previous)
    baseline = system_snapshot()
    baseline.update(
        ledger_count=len(previous),
        ledger_rows_sha256=digest(previous),
        lineage_run=OLD.relative_to(ROOT).as_posix(),
        services=subprocess.check_output(
            [DOCKER, "ps", "--format", "{{.Names}} {{.ID}}"], text=True
        ).splitlines(),
    )
    with sqlite3.connect(PARENT / "execution-ledger.sqlite3") as source:
        with sqlite3.connect(RUN / "ledger-before.sqlite3") as target:
            source.backup(target)
    protected = {}
    for directory in [
        OLD,
        PARENT,
        ROOT / "data/evaluation/medresident-benchmark-v1",
        ROOT / "local_model_testing/retrieval_integration",
        ROOT / "model-training/src/medical",
        ROOT / "model-training/src/teaching",
        ROOT / "adapter",
    ]:
        for path in directory.rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and not path.name.startswith("execution-ledger.sqlite3")
            ):
                protected[path.relative_to(ROOT).as_posix()] = file_hash(path)
    protected[".env"] = file_hash(ROOT / ".env")
    for name in [
        "medical-development.json",
        "development-questions.json",
        "planned-medical-payloads.json",
        "payload-token-audit.json",
        "pre-model-configuration.json",
    ]:
        shutil.copy2(OLD / name, RUN / name)
    source_hashes = {
        p.relative_to(ROOT).as_posix(): file_hash(p)
        for p in [
            CORPUS / "corpus.jsonl",
            CORPUS / "vectors.npy",
            CORPUS / "index-manifest.json",
            CORPUS / "source-manifest.json",
            CORPUS / "catalog.json",
            ENCODER / "manifest.json",
            ROOT / "apps/backend/app/ai/retrieval/book_mapping.v1.json",
        ]
    }
    write(
        RUN / "authorization.json",
        {
            "created": datetime.now(UTC).isoformat(),
            "supplement_max_attempts": 12,
            "shared_total_ceiling": 800,
            "baseline_actual_count": len(previous),
            "category": "medical_retrieval_confirmation",
            "configs": ["retrieval_medical_vector_v2", "retrieval_medical_hybrid_v2"],
            "request_sha256": file_hash(
                "C:/Users/huyho/.codex/attachments/f175c6aa-4af1-4073-872e-023d3e482167/Pasted text.txt"
            ),
            "smoke_or_warmup_generations": 0,
            "teaching": "explicit mock",
            "retry": "none",
            "lineage": baseline["lineage_run"],
            "after_this_run": "closed; reporting only",
        },
    )
    write(
        RUN / "configuration.json",
        {
            "revision": "retrieval-confirmation-v2",
            "lineage": baseline["lineage_run"],
            "model_generation_retrieval_and_references_unchanged": True,
            "source_hashes": source_hashes,
            "copied_reference_hashes": {
                n: file_hash(RUN / n)
                for n in ["medical-development.json", "planned-medical-payloads.json"]
            },
            "http_read_seconds": 600,
            "practice_medical_deadline_seconds": 625,
            "readiness_load_timeout_seconds": 1200,
            "host_load_minimum_GiB": 6,
            "batch_concurrency": 1,
            "order": "sample pairs: vector then hybrid; ST_CLOSE correct first",
            "worker_gate": "actual service lock + generation active/started/finished; readiness is load only",
            "vector_kg_queries": 0,
            "hybrid_expected_queries_per_request": 2,
            "schema_failure_policy": "keep raw; continue only if worker idle and generation ended",
            "infrastructure_failure_policy": "stop batch, preserve partial results, no retry",
        },
    )
    write(RUN / "protected-before.json", protected)
    write(RUN / "baseline.json", baseline)
    print(
        {
            "new_run": RUN.name,
            "baseline_ledger_actual": len(previous),
            "new_cap": 12,
            "protected_files": len(protected),
            "available_RAM_GiB": round(
                baseline["system"]["ram_available_bytes"] / 1024**3, 2
            ),
        }
    )


if __name__ == "__main__":
    main()
