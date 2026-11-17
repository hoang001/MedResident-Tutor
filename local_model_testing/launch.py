"""Windows controller for one disposable GPU batch container with a durable venv.

Works without changing PowerShell's execution policy. Never changes app provider.
"""

import argparse
import os
import subprocess
from pathlib import Path

from .artifacts import check
from .common import ROOT, REPORT, read, write, system_snapshot

DOCKER = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
CID = REPORT / "worker-container.cid"
IMAGE = "medresident-tutor-backend:latest"


def docker(*args, **kwargs):
    return subprocess.run([str(DOCKER), *args], check=True, **kwargs)


def stop():
    if not CID.exists():
        print("No owned model container; no process stopped.")
        return
    cid = CID.read_text().strip()
    if len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid):
        raise ValueError("INVALID_CONTAINER_RECORD")
    exists = docker(
        "ps",
        "--all",
        "--no-trunc",
        "--filter",
        "id=" + cid,
        "--format",
        "{{.ID}}",
        capture_output=True,
        text=True,
    ).stdout.strip()
    pid, status = None, "already_exited_and_removed"
    if exists:
        import json

        info = json.loads(
            docker("inspect", cid, capture_output=True, text=True).stdout
        )[0]
        labels = info["Config"].get("Labels", {})
        if (
            labels.get("medresident.local-model-test") != "1"
            or labels.get("medresident.project") != str(ROOT)
            or info["Config"]["Image"] != IMAGE
        ):
            raise ValueError("CONTAINER_OWNERSHIP_MISMATCH; refusing stop")
        pid = info["State"]["Pid"]
        if info["State"]["Running"]:
            docker("stop", "--time", "30", cid, capture_output=True)
            status = "stopped_owned_container"
        else:
            status = "owned_container_exited"
    CID.unlink()
    write(
        REPORT / "container-stop.json",
        {
            "container_id": cid,
            "docker_wsl_pid": pid,
            "status": status,
            "after": system_snapshot(),
        },
    )
    print(status, cid[:12], "Docker/WSL PID", pid)


def start(kind, smoke, serve=False):
    REPORT.mkdir(parents=True, exist_ok=True)
    if (REPORT / "local-profile.json").exists() and (kind != "medical" or not serve):
        raise RuntimeError(
            "LOCAL_PROFILE_MEDICAL_HTTP_ONLY; no batch smoke or Teaching model"
        )
    if CID.exists():
        raise RuntimeError("OWNED_CONTAINER_RECORD_EXISTS; run launch stop first")
    check(kind)
    host = system_snapshot()
    if host["system"]["ram_available_bytes"] < 4 * 1024**3:
        raise RuntimeError("WINDOWS_AVAILABLE_RAM_BELOW_4_GIB; refusing model load")
    probe = read(REPORT / "runtime-probe.json")
    if probe.get("status") != "runtime_probe_passed_not_model_test":
        raise RuntimeError("DOCKER_CUDA_NF4_RUNTIME_NOT_VERIFIED")
    import socket

    for port in (8101, 8102):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("EXISTING_MODEL_LISTENER; refusing concurrent load")
    cmd = [
        str(DOCKER),
        "run",
        "--rm",
        "--pull",
        "never",
        "--gpus",
        "device=0",
        "--name",
        "medresident-local-" + kind + ("-http" if serve else "-batch"),
        "--label",
        "medresident.local-model-test=1",
        "--label",
        "medresident.project=" + str(ROOT),
        "--cidfile",
        str(CID),
        "--mount",
        "type=bind,source=" + str(ROOT) + ",target=/workspace",
        "--mount",
        "type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv",
        "-w",
        "/workspace",
        "-e",
        "HF_HUB_OFFLINE=1",
        "-e",
        "TRANSFORMERS_OFFLINE=1",
        "--entrypoint",
        "/opt/local-models-venv/bin/python",
        IMAGE,
        "-m",
        "local_model_testing.worker",
        kind,
    ]
    if smoke:
        cmd.append("--smoke")
    if serve:
        if kind != "medical" or not os.environ.get("MEDICAL_API_KEY"):
            raise RuntimeError("MEDICAL_HTTP_STAGE_REQUIRES_EPHEMERAL_AUTH")
        cmd.append("--serve")
        cmd[cmd.index("--entrypoint") : cmd.index("--entrypoint")] = [
            "-p",
            "127.0.0.1:8101:8101",
            "--network",
            os.environ["LOCAL_MODEL_TEST_NETWORK"],
            "-e",
            "MEDICAL_API_KEY",
        ]
    if os.environ.get("LOCAL_MODEL_TEST_RUN_ID"):
        cmd[cmd.index("--entrypoint") : cmd.index("--entrypoint")] = [
            "-e",
            "LOCAL_MODEL_TEST_RUN_ID=" + os.environ["LOCAL_MODEL_TEST_RUN_ID"],
        ]
    child = None
    try:
        with (
            REPORT / (kind + ("-http-controller.log" if serve else "-controller.log"))
        ).open("x", encoding="utf-8") as log:
            child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            print(
                "Owned controller PID",
                child.pid,
                "; foreground batch; inspect "
                + str(REPORT / (kind + "-controller.log")),
                flush=True,
            )
            code = child.wait()
            if code:
                raise RuntimeError(
                    "MODEL_WORKER_EXIT_"
                    + str(code)
                    + "; inspect saved report/log, no retry"
                )
    finally:
        try:
            stop()
        finally:
            if child is not None:
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    # This is our exact Docker client process, never a name-based kill.
                    child.terminate()
                    child.wait(timeout=10)
            write(REPORT / (kind + "-after-process-exit.json"), system_snapshot())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["medical", "teaching", "stop"])
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.action == "stop":
        stop()
    else:
        start(args.action, args.smoke, args.serve)


if __name__ == "__main__":
    main()
