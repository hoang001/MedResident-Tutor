import hashlib
import json
import os
import re
from pathlib import Path

from local_model_testing.common import ROOT, file_hash, read
from local_model_testing.common import write as write

DATA = ROOT / "data/evaluation/medresident-benchmark-v1"
RUNS = ROOT / "data/evaluation/runs"
RUN_ID = os.environ.get("MEDRESIDENT_EXPERIMENT_RUN", "benchmark-v1-20261110")
if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", RUN_ID):
    raise ValueError("Invalid experiment run ID")
RUN = RUNS / RUN_ID


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), encoding="utf-8")


def frozen():
    manifest = read(DATA / "manifest.json")
    for name, expected in manifest["files"].items():
        if file_hash(DATA / name) != expected:
            raise ValueError("Frozen benchmark changed: " + name)
    return manifest
