"""Connect the two saved real model outputs through BE contracts without regeneration."""

import json
import subprocess
import argparse

from .common import ROOT, REPORT, read, write, file_hash
from .launch import DOCKER


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-id",
        default="CLINICAL_DEMO_V1_CASE01__full",
        choices=[
            "CLINICAL_DEMO_V1_CASE01__full",
            "CLINICAL_DEMO_V1_CASE01__incorrect",
            "CLINICAL_DEMO_V1_XR01__partial",
            "CLINICAL_DEMO_V1_XR01__full",
        ],
    )
    cid = parser.parse_args().case_id
    destination = REPORT / (
        "practice-replay.json"
        if cid == "CLINICAL_DEMO_V1_CASE01__full"
        else "practice-replay-" + cid + ".json"
    )
    assert not destination.exists()
    medical = next(
        c for c in read(REPORT / "medical-batch.json")["cases"] if c["case_id"] == cid
    )
    teaching = next(
        c for c in read(REPORT / "teaching-batch.json")["cases"] if c["case_id"] == cid
    )
    assert medical["contract_valid"] and teaching["guarded_prediction"] is not None
    teaching_input = next(
        c["input"]
        for c in read(REPORT / "teaching-replay-inputs.json")
        if c["case_id"] == cid
    )
    assert teaching_input["medical_evaluation"] == medical["prediction"]
    credentials = read(ROOT / "data/backups/clinical-demo-accounts.json")["users"][0]
    payload = read(REPORT / "inputs" / (cid + ".json"))
    context = {
        "credentials": {k: credentials[k] for k in ("email", "password")},
        "question_id": cid.split("__")[0],
        "student_answer": payload["student_answer"],
        "replay": {
            "medical_input": payload,
            "medical_output": medical["prediction"],
            "teaching_input": teaching_input,
            "teaching_output": teaching["guarded_prediction"],
            "medical_source_sha256": file_hash(REPORT / "medical-batch.json"),
            "teaching_source_sha256": file_hash(REPORT / "teaching-batch.json"),
        },
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
        (s[len(marker) :] for s in result.stdout.splitlines() if s.startswith(marker)),
        None,
    )
    report = (
        json.loads(line)
        if line
        else {
            "status": "failed",
            "error": "No sanitized backend replay report",
            "returncode": result.returncode,
        }
    )
    write(destination, report)
    print(
        "BE replay completed:",
        report.get("completed"),
        "; rolled back:",
        report.get("test_attempt_absent_after_rollback"),
        "; new model calls: 0",
    )


if __name__ == "__main__":
    main()
