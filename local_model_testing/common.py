import hashlib
import json
import subprocess
import os
import platform
import shutil
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "data/local-models"
REPORT_BASE = ROOT / "data/local-model-tests"
RUN_ID = os.environ.get("LOCAL_MODEL_TEST_RUN_ID", "")
if RUN_ID and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", RUN_ID):
    raise ValueError("Invalid local model test run ID")
REPORT = REPORT_BASE / "runs" / RUN_ID if RUN_ID else REPORT_BASE
KINDS = {
    "medical": {
        "repo": "Qwen/Qwen3-4B-Instruct-2507",
        "name": "Qwen3-4B-Instruct-2507",
        "adapter": "model-training/outputs/medical-qwen3-pilot/adapter",
        "port": 8101,
    },
    "teaching": {
        "repo": "Qwen/Qwen2.5-7B-Instruct",
        "name": "Qwen2.5-7B-Instruct",
        "adapter": "model-training/outputs/teaching-qwen2.5-v1/adapter",
        "port": 8102,
    },
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ps(script):
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8-sig", errors="replace").strip()


def system_snapshot():
    if os.name != "nt":
        import psutil

        memory = psutil.virtual_memory()
        return {
            "time_utc": datetime.now(UTC).isoformat(),
            "scope": "Linux runtime/WSL memory, not Windows physical RAM",
            "system": {
                "os": platform.platform(),
                "ram_total_bytes": memory.total,
                "ram_available_bytes": memory.available,
                "disk_free_bytes": shutil.disk_usage(ROOT).free,
            },
            "gpu": subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
                    "--format=csv,noheader",
                ],
                text=True,
            ).strip(),
            "gpu_processes": subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,process_name,used_memory",
                    "--format=csv,noheader",
                ],
                text=True,
            ).splitlines(),
        }
    script = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $o=Get-CimInstance Win32_OperatingSystem; $d=Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"; @{os=$o.Caption;ram_total_bytes=$o.TotalVisibleMemorySize*1024;ram_available_bytes=$o.FreePhysicalMemory*1024;disk_free_bytes=$d.FreeSpace} | ConvertTo-Json -Compress"
    return {
        "time_utc": datetime.now(UTC).isoformat(),
        "system": json.loads(ps(script)),
        "gpu": subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip(),
        "gpu_processes": subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader",
            ],
            text=True,
        ).splitlines(),
    }
