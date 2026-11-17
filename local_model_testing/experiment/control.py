"""Owned, sequential Docker lifecycle for the independent experiment. No app/provider writes."""
import argparse
import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime

from local_model_testing.common import system_snapshot
from local_model_testing.launch import DOCKER, IMAGE

from .common import DATA, ROOT, RUN, RUN_ID, file_hash, frozen, read, write

CID = RUN / "active-container.cid"
CONFIGS = ["medical_base", "medical_adapter", "teaching_base", "teaching_adapter"]
STOP_REQUEST = RUN / "stop-request.json"
OWNER = RUN / "controller-owner.json"


def controller_identity(pid):
    script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
              f"$taskProcess=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}'; "
              "if ($taskProcess) { @{pid=$taskProcess.ProcessId; "
              "created=$taskProcess.CreationDate.ToUniversalTime().ToString('o'); "
              "command=$taskProcess.CommandLine} | ConvertTo-Json -Compress }")
    result = subprocess.check_output(["powershell", "-NoProfile", "-Command", script])
    return json.loads(result.decode("utf-8-sig")) if result.strip() else None


def request_stop():
    write(STOP_REQUEST, {"requested_at": datetime.now(UTC).isoformat(), "run_id": RUN_ID})
    if OWNER.exists():
        owner = read(OWNER)
        live = controller_identity(owner["pid"])
        if live and live["created"] == owner["created"]:
            if "local_model_testing.experiment.control run" not in live["command"]:
                raise RuntimeError("Controller PID ownership mismatch; refusing termination")
            # Stop the exact owned coordinator first, preventing the next config starting.
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f'Stop-Process -Id {int(owner["pid"])} -Force -ErrorAction Stop'],
                           check=True, capture_output=True)
            for _ in range(40):
                current = controller_identity(owner["pid"])
                if current is None or current["created"] != owner["created"]:
                    break
                time.sleep(.25)
            else:
                raise RuntimeError("Owned controller has not exited")
    stop()


def docker(*args, **kwargs):
    return subprocess.run([str(DOCKER), *args], check=True, **kwargs)


def owned_info(cid):
    if len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid):
        raise ValueError("Invalid owned CID")
    found = docker("ps", "-a", "--no-trunc", "--filter", "id="+cid, "--format", "{{.ID}}",
                   capture_output=True, text=True).stdout.strip()
    if not found:
        return None
    info = json.loads(docker("inspect", cid, capture_output=True, text=True).stdout)[0]
    labels = info["Config"].get("Labels", {})
    if (labels.get("medresident.experiment") != RUN_ID
            or labels.get("medresident.project") != str(ROOT)
            or info["Config"]["Image"] != IMAGE):
        raise ValueError("Ownership mismatch; refusing stop")
    return info


def stop():
    if not CID.exists():
        print("No owned experiment container", flush=True)
        return
    cid = CID.read_text().strip()
    info = owned_info(cid)
    if info and info["State"]["Running"]:
        docker("stop", "--time", "30", cid, capture_output=True)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        remaining = owned_info(cid)
        if remaining is None or not remaining["State"]["Running"]:
            break
        time.sleep(.5)
    else:
        raise RuntimeError("Owned worker has not exited; not declaring cleanup")
    write(RUN / ("stop-" + cid[:12] + ".json"), {"container_id": cid,
        "docker_wsl_pid": info["State"]["Pid"] if info else None, "exited": True,
        "after_exit": system_snapshot()})
    CID.unlink()


def protect():
    target = RUN / "protected-hashes.json"
    if target.exists():
        for path, digest in read(target).items():
            assert file_hash(ROOT / path) == digest, "Protected artifact changed: " + path
        return
    result = {}
    for relative in ("model-training", "data/training", "data/processed", "data/integration",
                     "data/local-model-tests", "adapter", "data/graduate", "apps/backend", "apps/frontend"):
        for path in (ROOT / relative).rglob("*"):
            if (not any(p in {"__pycache__", "node_modules", ".next", "test-results"}
                                           for p in path.parts) and path.is_file()
                    and path.suffix not in {".pyc", ".log", ".tsbuildinfo"}):
                result[path.relative_to(ROOT).as_posix()] = file_hash(path)
    result[".env"] = file_hash(ROOT / ".env")
    write(target, result)


def run(config):
    frozen()
    RUN.mkdir(parents=True, exist_ok=True)
    if CID.exists():
        raise RuntimeError("An owned worker is active; do not launch a second coordinator")
    if OWNER.exists():
        owner = read(OWNER)
        live = controller_identity(owner["pid"])
        if live and live["created"] == owner["created"]:
            raise RuntimeError("An owned coordinator is active; ownership record not overwritten")
    selected_configs = CONFIGS if config == "all" else [config]
    if all((RUN/(name+"-process.json")).exists()
           and read(RUN/(name+"-process.json"))["status"] == "finished"
           for name in selected_configs):
        for name in selected_configs:
            print(name, "completed checkpoint reused; no reload/generation", flush=True)
        return  # Preserve original end time, owner and budget on completed-run reuse.
    if STOP_REQUEST.exists():
        STOP_REQUEST.unlink()  # Explicit new run command resumes this stopped experiment.
    write(OWNER, controller_identity(os.getpid()))
    pointer = DATA / "execution.json"
    if pointer.exists():
        if read(pointer)["run_id"] != RUN_ID:
            raise RuntimeError("Dataset already assigned to a run; refuse budget reset")
    else:
        write(pointer, {"run_id": RUN_ID, "budget_scope": "all invocations of this dataset revision"})
    protect()
    if not (RUN / "baseline.json").exists():
        service_ids = docker("ps", "--format", "{{.Names}} {{.ID}}", capture_output=True, text=True).stdout
        write(RUN / "baseline.json", {"host": system_snapshot(), "services": service_ids.splitlines(),
                                      "model_inference_scope": "standalone batch, not HTTP integration"})
    for name in selected_configs:
        if STOP_REQUEST.exists():
            break
        summary = RUN / (name + "-process.json")
        if summary.exists() and read(summary)["status"] == "finished":
            print(name, "completed checkpoint reused; no reload/generation", flush=True)
            continue
        if CID.exists():
            raise RuntimeError("Owned CID exists; inspect/stop before resuming")
        snapshot = system_snapshot()
        if snapshot["system"]["ram_available_bytes"] < 4 * 1024**3:
            raise RuntimeError("Host available RAM below 4 GiB; no model load")
        for port in (8101, 8102):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Model listener already exists; refusing concurrent load")
        cmd = [str(DOCKER), "run", "--rm", "--pull", "never", "--gpus", "device=0",
               "--network", "none", "--name", "medresident-experiment-" + name.replace("_", "-"),
               "--label", "medresident.experiment=" + RUN_ID, "--label", "medresident.project="+str(ROOT),
               "--cidfile", str(CID),
               "--mount", "type=bind,source="+str(ROOT)+",target=/workspace,readonly",
               "--mount", "type=bind,source="+str(RUN)+",target=/workspace/data/evaluation/runs/"+RUN_ID,
               "--mount", "type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv",
               "-w", "/workspace", "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1",
               "-e", "HF_HUB_DISABLE_TELEMETRY=1", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "MEDRESIDENT_EXPERIMENT_RUN="+RUN_ID,
               "--entrypoint", "/opt/local-models-venv/bin/python", IMAGE,
               "-m", "local_model_testing.experiment.worker", name]
        child = None
        host_samples = []
        try:
            stamp = str(time.time_ns())
            with (RUN / (name + "-" + stamp + ".log")).open("x", encoding="utf-8") as log:
                child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                write(RUN / "controller.json", {"pid": os.getpid(), "docker_client_pid": child.pid,
                                               "config": name, "run_id": RUN_ID})
                print("Started", name, "; owned Docker client PID", child.pid, flush=True)
                low_memory = 0
                while child.poll() is None:
                    try:
                        child.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        sample = system_snapshot()
                        host_samples.append(sample)
                        write(RUN / (name + "-host-memory.json"), host_samples)
                        low_memory = low_memory+1 if sample["system"]["ram_available_bytes"] < 512*1024**2 else 0
                        if low_memory >= 3:
                            raise RuntimeError("Sustained host RAM below 512 MiB; stopping owned worker")
                if child.returncode:
                    print(name, "worker exit", child.returncode, "; no automatic retry", flush=True)
        finally:
            stop()
            if child is not None:
                child.wait(timeout=40)
            write(RUN / (name + "-after-container-exit.json"), system_snapshot())
        protect()
        if summary.exists():
            result = read(summary)
            print(name, result["status"], flush=True)
        # Continue independent configurations after a recorded failure, never retry it.
    write(RUN / "after-experiment.json", system_snapshot())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "stop"])
    parser.add_argument("--config", choices=CONFIGS+["all"], default="all")
    args = parser.parse_args()
    if args.action == "stop":
        request_stop()
    else:
        run(args.config)


if __name__ == "__main__":
    main()
