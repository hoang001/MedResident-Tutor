"""Opt-in base Qwen authoring worker. No adapter, no grading contract, no autostart."""

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/authoring/local-v1-20261112"
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
NAME = "medresident-authoring-local"


def write(name, value):
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def reserve(payload):
    """A separate ledger plus append-only category in the existing aggregate ledger."""
    from app.ai.retrieval.evidence import digest
    RUN.mkdir(parents=True, exist_ok=True)
    path = ROOT / "data/evaluation/runs/benchmark-v1-20261110/execution-ledger.sqlite3"
    with sqlite3.connect(RUN / "ledger.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, status TEXT)")
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT count(*) FROM attempts").fetchone()[0] >= 2:
            raise RuntimeError("AUTHORING_TWO_ATTEMPT_CAP")
        fingerprint = digest(payload)
        cur = db.execute("INSERT INTO attempts(fingerprint,status) VALUES(?,'started')", (fingerprint,))
        identifier = cur.lastrowid
    shared_id = None
    if path.exists():
        with sqlite3.connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM attempts").fetchone()[0] >= 800:
                raise RuntimeError("SHARED_LEDGER_CAP")
            cur = db.execute("INSERT INTO attempts(config,sample_id,category,fingerprint,started,status,generation_started) VALUES(?,?,'authoring',?,?,'started',1)",
                ("authoring_base_v1_20261112", str(identifier), fingerprint, datetime.now(UTC).isoformat()))
            shared_id = cur.lastrowid
    return identifier, shared_id


def finish(ids, status, raw=None, error=None):
    write(f"attempt-{ids[0]}.json", {"status": status, "raw": raw, "error_type": error,
                                   "adapter": None, "prompt_version": "authoring-v1"})
    with sqlite3.connect(RUN / "ledger.sqlite3") as db:
        db.execute("UPDATE attempts SET status=? WHERE id=?", (status, ids[0]))
    if ids[1]:
        with sqlite3.connect(ROOT / "data/evaluation/runs/benchmark-v1-20261110/execution-ledger.sqlite3") as db:
            db.execute("UPDATE attempts SET status=?,finished=?,reason=? WHERE id=? AND category='authoring'",
                (status, datetime.now(UTC).isoformat(), error, ids[1]))


def serve():
    sys.path[:0] = [str(ROOT / "model-training"), str(ROOT / "apps/backend")]
    import torch
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from app.modules.questions.authoring import ProposalRequest, Scope, VERSION, SYSTEM, validate_proposal
    from src.medical.inference import load_model
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    tokenizer, model = load_model(ROOT / "data/local-models/base/Qwen3-4B-Instruct-2507", local_files_only=True)
    app = FastAPI()
    lock = asyncio.Lock()

    @app.post("/authoring/propose")
    async def propose(body: dict):
        if lock.locked():
            raise HTTPException(429, "AUTHORING_BUSY")
        if body.get("version") != VERSION or body.get("system") != SYSTEM:
            raise HTTPException(422, "AUTHORING_VERSION_MISMATCH")
        scope = Scope.model_validate(body["scope"])
        evidence = body.get("evidence", [])
        if not evidence or sum(len(e["content"]) for e in evidence) > 6000:
            raise HTTPException(422, "EVIDENCE_REQUIRED_OR_OVER_BUDGET")
        async with lock:
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps({"scope": scope.model_dump(), "evidence": evidence}, ensure_ascii=False)}]
            inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
            n = inputs["input_ids"].shape[-1]
            if n > 4096:
                raise HTTPException(413, "AUTHORING_CONTEXT_TOO_LONG")
            ids = reserve(body)
            write(f"request-{ids[0]}.json", body)
            def generate():
                with torch.inference_mode():
                    output = model.generate(**{k: v.to(model.device) for k,v in inputs.items()}, max_new_tokens=1600, do_sample=False, pad_token_id=tokenizer.pad_token_id)
                return tokenizer.decode(output[0,n:], skip_special_tokens=True)
            # Shield generation and keep lock until GPU work ends even if caller disconnects.
            task = asyncio.create_task(asyncio.to_thread(generate))
            raw = None
            try:
                try:
                    raw = await asyncio.shield(task)
                except asyncio.CancelledError:
                    raw = await task
                    raise
                value = validate_proposal(json.loads(raw), evidence, scope.max_score)
                finish(ids, "completed", raw)
                return value
            except BaseException as exc:
                finish(ids, "failed", raw, type(exc).__name__)
                raise HTTPException(502, "AUTHORING_OUTPUT_INVALID:" + type(exc).__name__) from None

    uvicorn.run(app, host="0.0.0.0", port=8103, access_log=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "serve"])
    args = parser.parse_args()
    if args.action == "serve":
        return serve()
    if args.action == "stop":
        info=json.loads(subprocess.check_output([DOCKER,"inspect",NAME],text=True))[0]
        if info["Config"]["Labels"].get("medresident.task")!="authoring-v1":
            raise SystemExit("Refusing to stop an unowned container")
        return subprocess.run([DOCKER, "stop", NAME], check=True).returncode
    # Host RAM gate, without terminating any user applications.
    free = int(subprocess.check_output(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"], text=True).strip()) / 1024**2
    if free < 6:
        write("startup.json", {"status": "blocked_ram", "free_gib": free, "required_gib": 6, "generations": 0})
        raise SystemExit(f"Not loading model: {free:.2f} GiB RAM free; requires 6 GiB")
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True)
    if max(int(x) for x in gpu.split()) > 2000:
        raise SystemExit("Not loading authoring while another GPU workload may be active")
    command = [DOCKER,"run","-d","--rm","--name",NAME,"--label","medresident.task=authoring-v1","--gpus","all","-p","127.0.0.1:8103:8103",
        "--mount",f"type=bind,source={ROOT},target=/workspace","--mount","type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv",
        "-w","/workspace","-e","PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/usr/local/lib/python3.12/site-packages",
        "--entrypoint","/opt/local-models-venv/bin/python","medresident-tutor-backend:latest","-m","local_model_testing.authoring_runtime","serve"]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
