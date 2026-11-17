"""Initial audit/protection and download only a local CPU retrieval encoder; no generation."""

import json
import shutil
import sqlite3
import subprocess
import urllib.request

from .common import (
    ROOT,
    RUN,
    PARENT,
    CORPUS,
    ENCODER,
    file_hash,
    read,
    write,
    rows,
    jsonl,
    digest,
    system_snapshot,
)

DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    if not (RUN / "baseline.json").exists():
        baseline = system_snapshot()
        baseline["services"] = subprocess.check_output(
            [DOCKER, "ps", "--format", "{{.Names}} {{.ID}}"], text=True
        ).splitlines()
        source = (
            ROOT / "local_model_testing/retrieval_integration/audit_source.py"
        ).read_bytes()
        probe = subprocess.run(
            [DOCKER, "exec", "-i", "medresident-tutor-backend-1", "python", "-"],
            input=source,
            capture_output=True,
            check=True,
        )
        baseline["runtime_audit"] = json.loads(probe.stdout)
        with sqlite3.connect(PARENT / "execution-ledger.sqlite3") as db:
            db.row_factory = sqlite3.Row
            old = [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")]
            with sqlite3.connect(RUN / "parent-ledger-before.sqlite3") as backup:
                db.backup(backup)
        baseline["parent_attempts"] = len(old)
        baseline["parent_rows_sha256"] = digest(old)
        protected = {}
        for directory in (
            ROOT / "data/evaluation/medresident-benchmark-v1",
            PARENT,
            ROOT / "model-training/src/medical",
            ROOT / "model-training/src/teaching",
            ROOT / "adapter",
        ):
            for p in directory.rglob("*"):
                if (
                    p.is_file()
                    and "__pycache__" not in p.parts
                    and not p.name.startswith("execution-ledger.sqlite3")
                ):
                    protected[p.relative_to(ROOT).as_posix()] = file_hash(p)
        protected[".env"] = file_hash(ROOT / ".env")
        write(RUN / "protected-before.json", protected)
        write(RUN / "baseline.json", baseline)
        write(
            RUN / "authorization.json",
            {
                "supplement_max_attempts": 12,
                "shared_total_ceiling": 800,
                "parent_ledger": "../benchmark-v1-20261110/execution-ledger.sqlite3",
                "request_sha256": file_hash(
                    "C:/Users/huyho/.codex/attachments/5096af0a-6ff6-4afe-91d4-2e255d94054c/Pasted text.txt"
                ),
                "new_smoke_generations": 0,
                "teaching": "explicit mock",
                "only_medical_adapter": True,
            },
        )
        print(
            "Audited current source/runtime; no generation. Parent attempts:",
            len(old),
            flush=True,
        )
    CORPUS.mkdir(parents=True, exist_ok=True)
    if not (CORPUS / "corpus.jsonl").exists():
        samples = rows(ROOT / "data/evaluation/medresident-benchmark-v1/corpus.jsonl")
        jsonl(CORPUS / "corpus.jsonl", samples)
        shutil.copy2(ROOT / "data/library/catalog.json", CORPUS / "catalog.json")
        write(
            CORPUS / "source-manifest.json",
            {
                "corpus_sha256": file_hash(CORPUS / "corpus.jsonl"),
                "catalog_sha256": file_hash(CORPUS / "catalog.json"),
                "chunks": len(samples),
                "contents": "Source OCR windows and source-checked PDF transcriptions only; no questions/expected/answer variants",
                "upstream_source_artifact": "data/evaluation/medresident-benchmark-v1/corpus.jsonl",
            },
        )
    ENCODER.mkdir(parents=True, exist_ok=True)
    manifest = ENCODER / "manifest.json"
    if manifest.exists():
        record = read(manifest)
        assert all(file_hash(ENCODER / n) == v for n, v in record["sha256"].items())
        print(
            "Local retrieval encoder reused; no Medical/Teaching model changed",
            flush=True,
        )
        return
    api = "https://huggingface.co/api/models/intfloat/multilingual-e5-small"
    with urllib.request.urlopen(api, timeout=30) as response:
        info = json.load(response)
    revision = info["sha"]
    available = {r["rfilename"] for r in info["siblings"]}
    names = [
        n
        for n in (
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "sentencepiece.bpe.model",
            "model.safetensors",
        )
        if n in available
    ]
    assert "model.safetensors" in names and "tokenizer.json" in names
    for name in names:
        path = ENCODER / name
        if path.exists():
            continue
        temporary = path.with_suffix(path.suffix + ".part")
        url = f"https://huggingface.co/intfloat/multilingual-e5-small/resolve/{revision}/{name}"
        with (
            urllib.request.urlopen(url, timeout=60) as source,
            temporary.open("wb") as destination,
        ):
            shutil.copyfileobj(source, destination, 1024 * 1024)
        temporary.replace(path)
        print("Retrieved CPU encoder artifact:", name, path.stat().st_size, flush=True)
    write(
        manifest,
        {
            "model": "intfloat/multilingual-e5-small",
            "revision": revision,
            "purpose": "local CPU semantic retrieval only; not a new grading/generative model",
            "model_card": "https://huggingface.co/intfloat/multilingual-e5-small",
            "sha256": {n: file_hash(ENCODER / n) for n in names},
        },
    )


if __name__ == "__main__":
    main()
