"""Read-only progress plus owned GPU container identity capture; never starts/stops a model."""
import json
from collections import Counter

from .common import RUN, read, write
from .control import CID, owned_info
from .ledger import report


def main():
    attempts = report()
    progress = {}
    for config in ("medical_base", "medical_adapter", "teaching_base", "teaching_adapter"):
        group = [r for r in attempts if r["config"] == config]
        progress[config] = {"attempts": len(group), "generations_started": sum(r["generation_started"] for r in group),
                            "statuses": dict(Counter(r["status"] for r in group))}
    owned = None
    if CID.exists():
        cid = CID.read_text().strip()
        info = owned_info(cid)
        if info:
            owned = {"container_id": cid, "docker_wsl_pid": info["State"]["Pid"],
                     "container_name": info["Name"], "running": info["State"]["Running"],
                     "image_id": info["Image"], "started_at": info["State"]["StartedAt"],
                     "gpu_request": info["HostConfig"].get("DeviceRequests")}
            target = RUN / "ownership" / (cid+".json")
            if not target.exists():
                write(target, owned)
    print(json.dumps({"progress": progress, "owned_container": owned,
                      "attempts_total": len(attempts), "generation_calls_started": sum(r["generation_started"] for r in attempts)}))


if __name__ == "__main__":
    main()
