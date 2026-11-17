"""Handle an auto-remove race using only the exact recorded owned container."""

import json
import subprocess
import time

from .common import ROOT, RUN, read, system_snapshot, write
from .control import CID, DOCKER


def inspect_owned(cid):
    result = subprocess.run([DOCKER, "inspect", cid], capture_output=True)
    if result.returncode:
        if b"no such object" in result.stderr.lower():
            return None
        raise RuntimeError("Owned container inspect failed; details suppressed")
    info = json.loads(result.stdout)[0]
    labels = info["Config"].get("Labels", {})
    assert labels.get("medresident.retrieval-supplement") == RUN.name
    assert labels.get("medresident.project") == str(ROOT)
    assert info["Config"]["Image"] == "medresident-tutor-backend:latest"
    return info


def main():
    if not CID.exists():
        return
    cid = CID.read_text().strip()
    assert len(cid) == 64 and all(c in "0123456789abcdef" for c in cid)
    ownership = read(RUN / "model-ownership.json")
    assert ownership["container_id"] == cid, "CID does not match recorded ownership"
    info = inspect_owned(cid)
    if info and info["State"]["Running"]:
        result = subprocess.run(
            [DOCKER, "stop", "--time", "40", cid], capture_output=True
        )
        if result.returncode and inspect_owned(cid) is not None:
            raise RuntimeError("Owned container did not stop")
    deadline = time.monotonic() + 45
    while True:
        info = inspect_owned(cid)
        if info is None or not info["State"]["Running"]:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Owned container exit not confirmed")
        time.sleep(0.5)
    archive = RUN / ("exited-" + cid[:12] + ".cid")
    assert not archive.exists(), "Exit ownership record already archived"
    CID.rename(archive)
    write(
        RUN / "owned-resources-exit.json",
        {
            "container_id": cid,
            "recorded_docker_wsl_pid": ownership["docker_wsl_pid"],
            "container_absent_or_exited": True,
            "cid_record_archived": archive.name,
            "only_exact_owned_model_container_considered": True,
            "after_exit": system_snapshot(),
        },
    )
    print("Exact owned model container exit confirmed; stale CID archived")


if __name__ == "__main__":
    main()
