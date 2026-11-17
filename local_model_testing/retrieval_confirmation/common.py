import hashlib
import json
from pathlib import Path

from local_model_testing.common import ROOT, file_hash, read, system_snapshot, write

RUN = ROOT / "data/evaluation/runs/retrieval-confirmation-20261111"
PARENT = ROOT / "data/evaluation/runs/benchmark-v1-20261110"
CORPUS = ROOT / "data/retrieval/book-corpus-v1"
ENCODER = ROOT / "data/local-models/embeddings/multilingual-e5-small"


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def rows(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values),
        encoding="utf-8",
    )


__all__ = [
    "ROOT",
    "RUN",
    "PARENT",
    "CORPUS",
    "ENCODER",
    "read",
    "write",
    "file_hash",
    "system_snapshot",
]
