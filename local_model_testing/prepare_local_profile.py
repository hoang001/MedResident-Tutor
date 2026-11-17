"""Create an immutable-input, Medical-only experiment without changing adapters."""

import shutil
import subprocess
from datetime import UTC, datetime

from .common import ROOT, REPORT_BASE, MODELS, read, write, file_hash, system_snapshot
from .launch import DOCKER
from .run_local_profile import LocalProfile


def main():
    profile = LocalProfile.model_validate(
        read(ROOT / "local_model_testing/profiles/local-medical.json")
    )
    running = subprocess.check_output(
        [str(DOCKER), "ps", "--format", "{{.Names}}"], text=True
    ).splitlines()
    assert not any(
        n.startswith(("medresident-local-medical-", "medresident-local-teaching-"))
        for n in running
    ), "Stop owned model before creating another run"
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-local90"
    destination = REPORT_BASE / "runs" / run_id
    destination.mkdir(parents=True, exist_ok=False)
    old = REPORT_BASE / "runs/20261109T063733Z"
    for name in ("download-plan.json", "medical-download.json", "runtime-probe.json"):
        shutil.copy2(REPORT_BASE / name, destination / name)
    shutil.copy2(
        old / "integration-inputs.json", destination / "integration-inputs.json"
    )
    for name in ("inputs", "expected"):
        shutil.copytree(old / name, destination / name)
    shutil.copy2(
        ROOT / "local_model_testing/profiles/local-medical.json",
        destination / "local-profile.json",
    )
    write(
        destination / "generation-budget.json",
        dict(limit=profile.max_generations, calls_started=0, calls_finished=0),
    )
    write(
        destination / "old-run-hashes.json",
        {
            p.relative_to(old).as_posix(): file_hash(p)
            for p in old.rglob("*")
            if p.is_file()
        },
    )
    baseline = system_snapshot()
    baseline["services"] = subprocess.check_output(
        [str(DOCKER), "ps", "--format", "{{.Names}} {{.Ports}}"], text=True
    ).splitlines()
    baseline["provider"] = subprocess.check_output(
        [
            str(DOCKER),
            "exec",
            "medresident-tutor-backend-1",
            "python",
            "-c",
            "import json; from app.core.config import get_settings; c=get_settings(); print(json.dumps(dict(app_env=c.app_env,practice_provider=c.practice_provider,model_calls_enabled=c.model_calls_enabled)))",
        ],
        text=True,
    ).strip()
    write(destination / "baseline.json", baseline)
    write(
        destination / "protected-file-hashes.json",
        read(old / "protected-file-hashes.json"),
    )
    write(
        destination / "frozen-medical-manifest.json",
        read(MODELS / "locked-adapters.json")["medical"],
    )
    write(
        REPORT_BASE / "active-run.json",
        dict(run_id=run_id, report_directory=str(destination)),
    )
    print(
        "Prepared",
        run_id,
        "; no generation. Run offline investigation and deadline tests before live requests.",
    )


if __name__ == "__main__":
    main()
