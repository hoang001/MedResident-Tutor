"""Owned local supplement lifecycle. Secrets only in process env/stdin, never command text."""

import argparse
import json
import os
import subprocess
import socket
import secrets
import time
from datetime import UTC, datetime

from .common import ROOT, RUN, CORPUS, PARENT, read, write, file_hash, system_snapshot
from . import ledger

DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
CID = RUN / "medical-container.cid"
OWNER = RUN / "controller-owner.json"
IMAGE = "medresident-tutor-backend:latest"


def freeze():
    audit = read(RUN / "payload-token-audit.json")
    preflight = read(RUN / "preflight.json")
    assert (
        audit["all_complete"]
        and audit["planned_inputs"] == 12
        and audit["generation_calls"] == 0
    )
    assert (
        len(preflight["cases"]) == 30
        and preflight["test_attempts_and_questions_absent_after_rollback"]
    )
    assert all(
        c["attempt"]["retrieval"]["effective_strategy"] == c["mode"]
        for c in preflight["cases"]
    )
    for mode in ("vector", "hybrid"):
        assert sum(c["mode"] == mode for c in preflight["cases"]) == 15
    target = RUN / "experiment-manifest.json"
    if target.exists():
        for name, sha in read(target)["files"].items():
            assert file_hash(ROOT / name) == sha, (
                "Frozen supplementary input/code changed"
            )
        return
    files = [
        ROOT / "apps/backend/app/integration/reader.py",
        ROOT / "apps/backend/app/core/config.py",
        ROOT / "apps/backend/app/modules/practice/service.py",
        ROOT / "apps/backend/app/modules/practice/router.py",
        ROOT / "apps/backend/app/modules/practice/providers.py",
        ROOT / "apps/backend/app/modules/practice/contracts.py",
        ROOT / "model-training/src/medical/inference.py",
        ROOT / "model-training/src/medical/validation.py",
    ]
    files += list((ROOT / "apps/backend/app/ai/retrieval").glob("*.py"))
    files += [ROOT / "apps/backend/app/ai/retrieval/book_mapping.v1.json"]
    files += [
        ROOT / "local_model_testing/retrieval_integration" / n
        for n in (
            "common.py",
            "control.py",
            "backend.py",
            "ledger.py",
            "medical_server.py",
        )
    ]
    files += [
        CORPUS / n
        for n in (
            "corpus.jsonl",
            "catalog.json",
            "source-manifest.json",
            "index-manifest.json",
            "vectors.npy",
        )
    ]
    files += [
        RUN / n
        for n in (
            "authorization.json",
            "pre-model-configuration.json",
            "development-questions.json",
            "medical-development.json",
            "planned-medical-payloads.json",
            "payload-token-audit.json",
            "preflight.json",
        )
    ]
    write(
        target,
        {
            "frozen_at": datetime.now(UTC).isoformat(),
            "parent_ledger": str(PARENT.relative_to(ROOT)),
            "parent_initial_attempts": read(RUN / "baseline.json")["parent_attempts"],
            "supplement_cap": 12,
            "model_inputs": 12,
            "sample_ids_shared_between_retrieval_branches": True,
            "files": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in files},
        },
    )


def owned_info():
    if not CID.exists():
        return None
    cid = CID.read_text().strip()
    if len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid):
        raise ValueError("Invalid owned CID")
    found = subprocess.check_output(
        [
            DOCKER,
            "ps",
            "-a",
            "--no-trunc",
            "--filter",
            "id=" + cid,
            "--format",
            "{{.ID}}",
        ],
        text=True,
    ).strip()
    if not found:
        return None
    info = json.loads(subprocess.check_output([DOCKER, "inspect", cid]))[0]
    labels = info["Config"].get("Labels", {})
    assert labels.get("medresident.retrieval-supplement") == RUN.name
    assert labels.get("medresident.project") == str(ROOT)
    assert info["Config"]["Image"] == IMAGE
    return info


def stop_worker():
    if not CID.exists():
        return
    info = owned_info()
    cid = CID.read_text().strip()
    pid = info["State"]["Pid"] if info else None
    if info and info["State"]["Running"]:
        subprocess.run(
            [DOCKER, "stop", "--time", "40", cid], capture_output=True, check=True
        )
    until = time.monotonic() + 45
    while time.monotonic() < until:
        info = owned_info()
        if info is None or not info["State"]["Running"]:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Owned model worker did not exit")
    write(
        RUN / "model-container-exit.json",
        {
            "cid": cid,
            "docker_wsl_pid": pid,
            "exited": True,
            "after_exit": system_snapshot(),
        },
    )
    CID.unlink()


def stop():
    # The owner record checks PID creation time, so a reused unrelated PID survives.
    from local_model_testing.experiment.control import controller_identity

    if OWNER.exists():
        owner = read(OWNER)
        live = controller_identity(owner["pid"])
        if live and live["created"] == owner["created"]:
            assert (
                "local_model_testing.retrieval_integration.control run"
                in live["command"]
            )
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Stop-Process -Id {int(owner['pid'])} -Force -ErrorAction Stop",
                ],
                check=True,
                capture_output=True,
            )
    # Kill only the owned supplemental backend child (its transaction rolls back).
    name = "medresident-retrieval-live"
    ids = subprocess.check_output(
        [
            DOCKER,
            "ps",
            "-q",
            "--filter",
            "name=^/" + name + "$",
            "--filter",
            "label=medresident.retrieval-supplement=" + RUN.name,
        ],
        text=True,
    ).split()
    for identifier in ids:
        subprocess.run(
            [DOCKER, "stop", "--time", "15", identifier],
            check=True,
            capture_output=True,
        )
    stop_worker()


def run():
    from local_model_testing.experiment.control import controller_identity

    freeze()
    if (RUN / "live.json").exists():
        print("Recorded supplement retained; no rerun or additional generation")
        return
    assert not CID.exists(), "An owned worker record exists; inspect before running"
    if OWNER.exists():
        owner = read(OWNER)
        live = controller_identity(owner["pid"])
        assert live is None or live["created"] != owner["created"], (
            "Coordinator already active"
        )
    assert len(ledger.attempts()) + 12 <= 800
    assert not [
        r for r in ledger.attempts() if r["category"] == "medical_retrieval_supplement"
    ], "No silent retry/resubmission"
    for port in (8101, 8102):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0, (
                "Another model listener already active"
            )
    assert system_snapshot()["system"]["ram_available_bytes"] >= 4 * 1024**3, (
        "RAM below safe load guard"
    )
    running_ids = subprocess.check_output([DOCKER, "ps", "-q"], text=True).split()
    info = (
        json.loads(subprocess.check_output([DOCKER, "inspect", *running_ids]))
        if running_ids
        else []
    )
    assert not any(c["HostConfig"].get("DeviceRequests") for c in info), (
        "Another GPU container active; not taking its GPU"
    )
    write(OWNER, controller_identity(os.getpid()))
    key = secrets.token_urlsafe(32)
    env, network = backend_environment()
    env.update(MEDICAL_API_KEY=key)
    command = [
        DOCKER,
        "run",
        "--rm",
        "--pull",
        "never",
        "--gpus",
        "device=0",
        "--name",
        "medresident-retrieval-medical",
        "--label",
        "medresident.retrieval-supplement=" + RUN.name,
        "--label",
        "medresident.project=" + str(ROOT),
        "--cidfile",
        str(CID),
        "--network",
        network,
        "-p",
        "127.0.0.1:8101:8101",
        "--mount",
        "type=bind,source=" + str(ROOT) + ",target=/workspace,readonly",
        "--mount",
        "type=bind,source="
        + str(RUN)
        + ",target=/workspace/data/evaluation/runs/"
        + RUN.name,
        "--mount",
        "type=bind,source="
        + str(PARENT)
        + ",target=/workspace/data/evaluation/runs/"
        + PARENT.name,
        "--mount",
        "type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv",
        "-w",
        "/workspace",
    ]
    for name in env:
        command += ["-e", name]
    command += [
        "--entrypoint",
        "/opt/local-models-venv/bin/python",
        IMAGE,
        "-m",
        "local_model_testing.retrieval_integration.medical_server",
    ]
    child = None
    samples = []
    try:
        with (RUN / "medical-server.log").open("x", encoding="utf-8") as log:
            child = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**os.environ, **env},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            import httpx

            until = time.monotonic() + 1200
            ready = False
            with httpx.Client(timeout=3) as client:
                while time.monotonic() < until:
                    if child.poll() is not None:
                        raise RuntimeError(
                            "Owned Medical process exited during startup"
                        )
                    try:
                        response = client.get("http://127.0.0.1:8101/ready")
                        if response.status_code == 200:
                            ready = True
                            break
                    except httpx.HTTPError:
                        pass
                    if CID.exists() and not (RUN / "model-ownership.json").exists():
                        owned = owned_info()
                        if owned:
                            write(
                                RUN / "model-ownership.json",
                                {
                                    "container_id": owned["Id"],
                                    "docker_wsl_pid": owned["State"]["Pid"],
                                    "image_id": owned["Image"],
                                    "started_at": owned["State"]["StartedAt"],
                                },
                            )
                    snapshot = system_snapshot()
                    samples.append(snapshot)
                    write(RUN / "host-memory.json", samples)
                    if len(samples) >= 3 and all(
                        s["system"]["ram_available_bytes"] < 512 * 1024**2
                        for s in samples[-3:]
                    ):
                        raise RuntimeError(
                            "Sustained host memory guard; no requests submitted"
                        )
                    time.sleep(5)
            assert ready, "Medical readiness deadline elapsed; no inference requested"
            print(
                "Medical HTTP ready; no smoke; running at most12 shared-ledger attempts",
                flush=True,
            )
            run_backend("live", key)
    finally:
        stop_worker()
        if child:
            child.wait(timeout=45)
        key = None
        write(RUN / "after-model-run.json", system_snapshot())


def backend_environment():
    info = json.loads(
        subprocess.check_output([DOCKER, "inspect", "medresident-tutor-backend-1"])
    )[0]
    current = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    names = (
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "APP_ENV",
        "SEED_ADMIN_EMAIL",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
    )
    env = {k: v for k, v in current.items() if k in names}
    env.update(
        DEBUG="false",
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONPATH="/workspace/apps/backend:/workspace:/workspace/model-training:/workspace/services/medical:/usr/local/lib/python3.12/site-packages",
        FILE_STORAGE_PATH="/workspace/data/uploads",
        KNOWLEDGE_DATA_ROOT="/workspace/data",
        MODEL_CALLS_ENABLED="false",
    )
    network = next(iter(info["NetworkSettings"]["Networks"]))
    return env, network


def run_backend(phase, key=None):
    env, network = backend_environment()
    if phase == "live":
        env.update(MODEL_CALLS_ENABLED="true", PRACTICE_PROVIDER="http")
    accounts = read(ROOT / "data/backups/clinical-demo-accounts.json")["users"]
    credentials = {k: accounts[0][k] for k in ("email", "password")}
    cmd = [
        DOCKER,
        "run",
        "--rm",
        "-i",
        "--name",
        "medresident-retrieval-" + phase,
        "--label",
        "medresident.retrieval-supplement=" + RUN.name,
        "--network",
        network,
        "--mount",
        "type=bind,source=" + str(ROOT) + ",target=/workspace",
        "--mount",
        "type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv",
        "-w",
        "/workspace",
    ]
    for name in env:
        cmd.extend(["-e", name])
    cmd.extend(
        [
            "--entrypoint",
            "/opt/local-models-venv/bin/python",
            "medresident-tutor-backend:latest",
            "-m",
            "local_model_testing.retrieval_integration.backend",
        ]
    )
    context = {"phase": phase, "credentials": credentials}
    if key:
        context.update(
            medical_url="http://medresident-retrieval-medical:8101", medical_key=key
        )
    result = subprocess.run(
        cmd,
        input=json.dumps(context).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **env},
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    for secret in [
        credentials["password"],
        key,
        *[v for n, v in env.items() if "PASSWORD" in n or "SECRET" in n or "URL" in n],
    ]:
        if secret:
            stdout = stdout.replace(secret, "[REDACTED]")
            stderr = stderr.replace(secret, "[REDACTED]")
    (RUN / (phase + "-runtime.log")).write_text(stderr, encoding="utf-8")
    lines = [
        line.split("=", 1)[1]
        for line in stdout.splitlines()
        if line.startswith("RETRIEVAL_INTEGRATION_REPORT=")
    ]
    if not lines:
        raise RuntimeError(
            "Isolated backend did not produce a report; inspect sanitized runtime log"
        )
    report = json.loads(lines[-1])
    write(RUN / (phase + ".json"), report)
    print(
        json.dumps(
            {
                "phase": phase,
                "status": report.get("status", "finished"),
                "cases": len(report.get("cases", [])),
                "model_attempts": report.get("model_attempts", 0),
                "error_type": report.get("error_type"),
                "assertion": report.get("assertion"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if report.get("status") == "failed":
        raise SystemExit(1)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "freeze", "run", "stop"])
    args = parser.parse_args()
    if args.action == "preflight":
        run_backend("preflight")
    elif args.action == "freeze":
        freeze()
    elif args.action == "run":
        run()
    elif args.action == "stop":
        stop()


if __name__ == "__main__":
    main()
