"""Run the reviewed adapter only against the already-verified local Compose backend."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structured", action="store_true")
    args = parser.parse_args()
    location = json.loads((ROOT / "data/clinical-cases/exercises/backup-location.json").read_text())
    backup = ROOT / location["folder"]
    assert (backup / "postgres.dump").stat().st_size > 0
    command = [DOCKER, "exec", "medresident-tutor-backend-1", "python", "-m", "app.integration.clinical_cases", "--bundle", "/app/data/clinical-cases/exercises"]
    if args.structured:
        command.append("--structured")
    reports = {}
    for name, extra in (("dry_run", []), ("apply", ["--apply"]), ("idempotent_repeat", ["--apply"])):
        result = json.loads(subprocess.check_output(command + extra))
        if name == "idempotent_repeat":
            assert all(q["action"] == "unchanged" for q in result["questions"])
        reports[name] = result
    target = ROOT / "data/clinical-cases/exercises"
    if args.structured:
        target /= "structured"
    (target / "import-results.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
