"""Restart only a recognised, owned model-service listener; never inspect/log secrets."""

import json
import math
import os
import signal
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from .validation import ServiceError

ENTRYPOINTS = {"medical_service.main:app", "medical_service.unified:app"}
PROC_ROOT = Path("/proc")


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    started: str
    uid: int
    is_model_service: bool


def process_identity(pid):
    proc = PROC_ROOT / str(pid)
    try:
        argv = (proc / "cmdline").read_bytes().decode(errors="replace").split("\0")
        stat = (proc / "stat").read_text()
        started = stat[stat.rfind(")") + 2 :].split()[19]
        uvicorn = any(Path(arg).name == "uvicorn" for arg in argv[:3])
        return ProcessIdentity(
            pid, started, proc.stat().st_uid, uvicorn and bool(ENTRYPOINTS.intersection(argv))
        )
    except (OSError, IndexError):
        return None


def port_is_free():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", 8000))
        return True
    except OSError:
        return False


def model_port_listeners():
    inodes = set()
    for name in ("tcp", "tcp6"):
        path = PROC_ROOT / "net" / name
        try:
            rows = path.read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            cols = row.split()
            if len(cols) > 9 and cols[1].endswith(":1F40") and cols[3] == "0A":
                inodes.add("socket:[" + cols[9] + "]")
    listeners = []
    try:
        processes = list(PROC_ROOT.iterdir())
    except OSError:
        return []
    for proc in processes:
        if not proc.name.isdigit():
            continue
        try:
            matches = False
            for fd in (proc / "fd").iterdir():
                try:
                    if os.readlink(fd) in inodes:
                        matches = True
                        break
                except OSError:
                    continue
        except OSError:
            continue
        if matches:
            identity = process_identity(int(proc.name))
            if identity:
                listeners.append(identity)
    return listeners


def ensure_port_available():
    if port_is_free():
        return
    listeners = model_port_listeners()
    if len(listeners) != 1:
        raise ServiceError("MODEL_SERVICE_LISTENER_AMBIGUOUS", 503)
    old = listeners[0]
    if old.pid <= 1 or old.pid == os.getpid():
        raise ServiceError("MODEL_SERVICE_REFUSE_PID1_OR_SELF", 503)
    if not old.is_model_service or old.uid != os.geteuid():
        raise ServiceError("MODEL_SERVICE_REFUSE_UNRELATED_PROCESS", 503)
    try:
        timeout = float(os.environ.get("MODEL_SERVICE_STOP_TIMEOUT_SECONDS", "60"))
    except ValueError:
        raise ServiceError("MODEL_SERVICE_STOP_TIMEOUT_INVALID", 503) from None
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ServiceError("MODEL_SERVICE_STOP_TIMEOUT_INVALID", 503)
    if process_identity(old.pid) != old:
        raise ServiceError("MODEL_SERVICE_PROCESS_CHANGED", 503)
    print(
        json.dumps({"stage": "RESTART", "status": "STOPPING_OLD_MODEL_SERVICE", "pid": old.pid}),
        flush=True,
    )
    try:
        os.kill(old.pid, signal.SIGTERM)
    except OSError:
        raise ServiceError("MODEL_SERVICE_STOP_FAILED", 503) from None
    deadline = time.monotonic() + timeout
    while process_identity(old.pid) == old:
        if time.monotonic() >= deadline:
            raise ServiceError("MODEL_SERVICE_STOP_TIMEOUT", 503)
        time.sleep(0.2)
    if not port_is_free():
        raise ServiceError("MODEL_SERVICE_PORT_UNAVAILABLE", 503)
    print(json.dumps({"stage": "RESTART", "status": "OLD_MODEL_SERVICE_STOPPED"}), flush=True)
