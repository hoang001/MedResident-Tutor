"""Ownership-checked stop. Never kills an unrecognised PID or an entire WSL/Docker VM."""

import argparse
import json
from datetime import UTC, datetime

import psutil

from .common import REPORT, read, write, system_snapshot

STATE = REPORT / "owned-worker.json"


def claim(kind):
    REPORT.mkdir(parents=True, exist_ok=True)
    proc = psutil.Process()
    state = {
        "pid": proc.pid,
        "created": proc.create_time(),
        "kind": kind,
        "executable": proc.exe(),
        "module": "local_model_testing.worker",
    }
    with STATE.open("x", encoding="utf-8") as stream:
        json.dump(state, stream)
    return state


def release(state):
    if STATE.exists() and read(STATE) == state:
        STATE.unlink()


def stop():
    if not STATE.exists():
        print("No model worker is owned by these scripts; no process stopped.")
        return
    state = read(STATE)
    try:
        proc = psutil.Process(state["pid"])
        if (
            abs(proc.create_time() - state["created"]) > 0.01
            or proc.exe().casefold() != state["executable"].casefold()
            or state["module"] not in proc.cmdline()
        ):
            raise RuntimeError("PID_IDENTITY_MISMATCH: refusing to stop")
        proc.terminate()
        proc.wait(timeout=30)
        status = "terminated_owned_worker"
    except psutil.NoSuchProcess:
        status = "already_exited"
    release(state)
    write(
        REPORT / "stop-result.json",
        {
            "status": status,
            "pid": state["pid"],
            "time": datetime.now(UTC).isoformat(),
            "after": system_snapshot(),
        },
    )
    print(status, state["pid"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["stop"])
    parser.parse_args()
    stop()
