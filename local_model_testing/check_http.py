"""Own one real Medical HTTP service, exercise BE child app, then unload it."""

import os
import secrets
import subprocess
import sys
import time
import json

import httpx

from .common import ROOT, REPORT, read, write, system_snapshot
from .launch import DOCKER, stop


def main():
    assert not (REPORT / "practice-http.json").exists(), (
        "No overwriting earlier HTTP test"
    )
    batch = read(REPORT / "medical-batch.json")
    assert batch.get("status") == "generations_finished_review_required"
    rows = [c for c in batch["cases"] if c.get("execution") == "local_real_adapter"]
    assert len(rows) == 8 and all(c.get("contract_valid") for c in rows), (
        "Medical contract failure; HTTP stage not entered"
    )
    inspection = json.loads(
        subprocess.check_output(
            [str(DOCKER), "inspect", "medresident-tutor-backend-1"], text=True
        )
    )[0]
    network = next(iter(inspection["NetworkSettings"]["Networks"]))
    environment = os.environ.copy()
    key = secrets.token_urlsafe(32)
    environment.update(MEDICAL_API_KEY=key, LOCAL_MODEL_TEST_NETWORK=network)
    child = None
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", "local_model_testing.launch", "medical", "--serve"],
            env=environment,
        )
        with httpx.Client(timeout=httpx.Timeout(10, connect=2)) as client:
            while True:
                if child.poll() is not None:
                    raise RuntimeError(
                        "Medical HTTP worker exited during load; inspect http controller log"
                    )
                try:
                    response = client.get("http://127.0.0.1:8101/ready")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)  # Readiness polling only. Never retries a generation.
        payload = read(REPORT / "inputs/CLINICAL_DEMO_V1_CASE01__full.json")
        credentials = read(ROOT / "data/backups/clinical-demo-accounts.json")["users"][
            0
        ]
        context = {
            "medical_url": "http://medresident-local-medical-http:8101",
            "medical_key": key,
            "credentials": {k: credentials[k] for k in ("email", "password")},
            "question_id": "CLINICAL_DEMO_V1_CASE01",
            "student_answer": payload["student_answer"],
        }
        code = (ROOT / "local_model_testing/backend_http_check.py").read_text(
            encoding="utf-8"
        )
        result = subprocess.run(
            [
                str(DOCKER),
                "exec",
                "-i",
                "medresident-tutor-backend-1",
                "python",
                "-c",
                code,
            ],
            input=json.dumps(context),
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        marker = "LOCAL_HTTP_REPORT="
        line = next(
            (
                s[len(marker) :]
                for s in result.stdout.splitlines()
                if s.startswith(marker)
            ),
            None,
        )
        if line is None:
            write(
                REPORT / "practice-http.json",
                {
                    "status": "failed",
                    "error": "backend child returned no sanitized report",
                    "returncode": result.returncode,
                },
            )
            raise RuntimeError("Backend HTTP inspection failed; no automatic retry")
        report = json.loads(line)
        report["medical_ready_http"] = 200
        report["readiness_scope"] = (
            "existing Medical FastAPI /ready; real loaded adapter"
        )
        write(REPORT / "practice-http.json", report)
        print(
            "Medical HTTP /ready 200; BE practice completed:",
            report.get("completed"),
            "; rollback verified:",
            report.get("test_attempt_absent_after_rollback"),
        )
    finally:
        stop()
        if child is not None:
            child.wait()
        write(REPORT / "after-medical-http-exit.json", system_snapshot())


if __name__ == "__main__":
    main()
