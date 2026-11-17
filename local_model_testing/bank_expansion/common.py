import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data/authoring/bank-expansion-20261116"
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
RUN.mkdir(parents=True, exist_ok=True)


def write(name, value):
    p = RUN / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read(name):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def inside(module, *args):
    info = json.loads(subprocess.check_output([DOCKER, "inspect", "medresident-tutor-backend-1"]))[0]
    env = dict(e.split("=", 1) for e in info["Config"]["Env"])
    env.update(PYTHONPATH="/workspace:/workspace/apps/backend:/workspace/model-training", KNOWLEDGE_DATA_ROOT="/workspace/data")
    env["MODEL_CALLS_ENABLED"] = "false"
    cmd = [DOCKER, "run", "--rm", "--name", "medresident-bank-expansion", "--network", next(iter(info["NetworkSettings"]["Networks"])),
        "--mount", f"type=bind,source={ROOT},target=/workspace", "-w", "/workspace"]
    for k in env: cmd += ["-e", k]
    cmd += ["medresident-tutor-backend:latest", "python", "-m", "local_model_testing.bank_expansion." + module, "--inside", *args]
    p = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True)
    out = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    for k,v in env.items():
        if v and any(s in k for s in ("KEY", "SECRET", "PASSWORD", "URL")): out = out.replace(v, "[REDACTED]")
    (RUN / (module + ".log")).write_text(out, encoding="utf-8")
    print(out[-6500:].encode("ascii", "backslashreplace").decode())
    if p.returncode: raise SystemExit(p.returncode)
