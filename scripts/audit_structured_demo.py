"""Hash immutable artifacts and compare existing PostgreSQL rows across the local change."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_clinical_demo import BACKEND, DOCKER, ROOT, ROW_SCRIPT

OUT = ROOT / "data/clinical-cases/exercises/structured/audit"


def hashes():
    result = {}
    for relative in ("data/local-model-tests/runs", "model-training", "adapter",
                     "data/clinical-cases/exercises/grading", "data/clinical-cases/exercises/learner"):
        for p in (ROOT / relative).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"}:
                result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finish", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    before = OUT / "protected-hashes.json"
    if not args.finish:
        assert not before.exists(), "Keep the original hash baseline"
        before.write_text(json.dumps(hashes(), indent=2), encoding="utf-8")
        print(json.dumps({"protected_files": len(json.loads(before.read_text()))}))
        return
    assert json.loads(before.read_text()) == hashes(), "Protected artifacts changed"
    location = json.loads((ROOT / "data/clinical-cases/exercises/backup-location.json").read_text())
    backup = ROOT / location["folder"]
    legacy_protected = json.loads((backup / "protected-file-hashes.json").read_text())
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
               for name, expected in legacy_protected.items())
    old = json.loads((backup / "rows-before.json").read_bytes())
    current = json.loads(subprocess.check_output(
        [DOCKER, "exec", "-i", BACKEND, "python", "-"], input=ROW_SCRIPT.encode()))
    (OUT / "rows-after.json").write_text(json.dumps(current), encoding="utf-8")
    kept = 0
    for table, rows in old.items():
        if table == "alembic_version":
            continue
        for row in rows:
            # Additive nullable column is expected; all original column values must match.
            assert any(all(candidate.get(k) == v for k, v in row.items())
                       for candidate in current[table]), "Existing row changed in " + table
            kept += 1
    old_mastery = old.get("learning_results", [])
    assert current.get("learning_results", []) == old_mastery
    summary = {"old_rows_preserved": kept, "protected_files_unchanged": len(hashes()),
               "original_backup_protected_files_unchanged": len(legacy_protected),
               "mastery_unchanged": True,
               "questions": [r["external_id"] for r in current["questions"]
                             if (r.get("external_id") or "").startswith("CLINICAL_DEMO_V2_")],
               "model_calls": 0}
    assert len(summary["questions"]) == 2
    (OUT / "integrity.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
