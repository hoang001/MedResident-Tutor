"""Bounded Medical-only live experiment; no extra smoke and no Teaching load."""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import math

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ROOT, REPORT, read, write, system_snapshot, file_hash
from .launch import DOCKER, CID, IMAGE, stop


class LocalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend_env: dict[str, str]
    readiness_load_seconds: float = Field(gt=0, le=3600)
    readiness_connect_seconds: float = Field(gt=0, le=10)
    readiness_read_seconds: float = Field(gt=0, le=30)
    max_generations: int = Field(ge=1, le=4)
    cases: list[str] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def coherent(self):
        allowed = {
            "PRACTICE_RUNTIME_PROFILE",
            "PRACTICE_LOCAL_MEDICAL_READ_SECONDS",
            "PRACTICE_LOCAL_CONNECT_SECONDS",
            "PRACTICE_LOCAL_WRITE_SECONDS",
            "PRACTICE_LOCAL_POOL_SECONDS",
            "PRACTICE_LOCAL_DEADLINE_GRACE_SECONDS",
        }
        if (
            set(self.backend_env) != allowed
            or self.backend_env["PRACTICE_RUNTIME_PROFILE"] != "local"
        ):
            raise ValueError("Only explicit local timeout fields are allowed")
        caps = {
            "PRACTICE_LOCAL_MEDICAL_READ_SECONDS": 600,
            "PRACTICE_LOCAL_CONNECT_SECONDS": 30,
            "PRACTICE_LOCAL_WRITE_SECONDS": 60,
            "PRACTICE_LOCAL_POOL_SECONDS": 30,
            "PRACTICE_LOCAL_DEADLINE_GRACE_SECONDS": 60,
        }
        for name, cap in caps.items():
            value = float(self.backend_env[name])
            if not math.isfinite(value) or not 0 < value <= cap:
                raise ValueError("Invalid local timeout: " + name)
        if (
            len(set(self.cases)) != len(self.cases)
            or len(self.cases) > self.max_generations
        ):
            raise ValueError("Duplicate cases or generation budget exceeded")
        if self.cases[:2] != [
            "CLINICAL_DEMO_V1_CASE01__full",
            "CLINICAL_DEMO_V1_XR01__full",
        ]:
            raise ValueError("Run both full-answer backend cases first")
        return self


def stop_service_and_wait(child):
    # Stop only our verified container; the launcher owns record removal/final log.
    if CID.exists():
        cid = CID.read_text().strip()
        assert len(cid) == 64 and all(c in "0123456789abcdef" for c in cid)
        exists = subprocess.check_output(
            [
                str(DOCKER),
                "ps",
                "--all",
                "--filter",
                "id=" + cid,
                "--format",
                "{{.ID}}",
            ],
            text=True,
        ).strip()
        if exists:
            info = json.loads(
                subprocess.check_output([str(DOCKER), "inspect", cid], text=True)
            )[0]
            assert info["Config"]["Labels"].get("medresident.project") == str(ROOT)
            assert (
                info["Config"]["Labels"].get("medresident.local-model-test") == "1"
                and info["Config"]["Image"] == IMAGE
            )
            write(
                REPORT / "medical-stop-identity.json",
                {"container_id": cid, "docker_wsl_pid": info["State"]["Pid"]},
            )
            subprocess.run(
                [str(DOCKER), "stop", "--time", "30", cid],
                check=True,
                stdout=subprocess.DEVNULL,
            )
    if child is not None:
        child.wait()
    if CID.exists():
        stop()


def main():
    assert all(
        file_hash(ROOT / name) == digest
        for name, digest in read(REPORT / "protected-file-hashes.json").items()
    ), "Frozen source/data changed"
    suite = ET.parse(REPORT / "deadline-tests.xml").getroot().find("testsuite")
    assert int(suite.get("failures", "0")) == int(suite.get("errors", "0")) == 0
    assert read(REPORT / "investigation.json")["inference_calls"] == 0, (
        "Offline investigation must finish first"
    )
    assert not (REPORT / "live-profile.json").exists(), (
        "No overwriting model experiment"
    )
    profile = LocalProfile.model_validate(read(REPORT / "local-profile.json"))
    assert read(REPORT / "generation-budget.json")["calls_started"] == 0
    cases = []
    for cid in profile.cases:
        # IDs must already be in the frozen integration manifest.
        assert cid in {
            r["case_id"] for r in read(REPORT / "integration-inputs.json")["cases"]
        }
        payload = read(REPORT / "inputs" / (cid + ".json"))
        assert payload["student_answer"].strip()
        cases.append(
            {
                "case_id": cid,
                "question_id": cid.split("__")[0],
                "student_answer": payload["student_answer"],
            }
        )
    source = REPORT / "backend-source"
    shutil.copytree(
        ROOT / "apps/backend/app",
        source / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / "model-training/src",
        source / "model-training/src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    info = json.loads(
        subprocess.check_output(
            [str(DOCKER), "inspect", "medresident-tutor-backend-1"], text=True
        )
    )[0]
    key = secrets.token_urlsafe(32)
    environment = os.environ.copy()
    environment.update(
        MEDICAL_API_KEY=key,
        LOCAL_MODEL_TEST_NETWORK=next(iter(info["NetworkSettings"]["Networks"])),
    )
    child = None
    started = time.monotonic()
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", "local_model_testing.launch", "medical", "--serve"],
            env=environment,
        )
        with httpx.Client(
            timeout=httpx.Timeout(
                profile.readiness_read_seconds,
                connect=profile.readiness_connect_seconds,
            )
        ) as client:
            while True:
                if child.poll() is not None:
                    raise RuntimeError(
                        "Medical service exited before readiness; inspect controller log"
                    )
                if time.monotonic() - started > profile.readiness_load_seconds:
                    raise TimeoutError("READINESS_LOAD_DEADLINE_EXCEEDED")
                try:
                    if client.get("http://127.0.0.1:8101/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        ready_seconds = time.monotonic() - started
        print(
            "Medical /ready 200 after",
            round(ready_seconds, 2),
            "seconds; running up to",
            profile.max_generations,
            "new generations",
            flush=True,
        )
        user = read(ROOT / "data/backups/clinical-demo-accounts.json")["users"][0]
        context = {
            "backend_source": "/app/data/local-model-tests/runs/"
            + REPORT.name
            + "/backend-source",
            "medical_url": "http://medresident-local-medical-http:8101",
            "medical_key": key,
            "credentials": {k: user[k] for k in ("email", "password")},
            "profile": profile.model_dump(),
            "cases": cases,
        }
        code = (ROOT / "local_model_testing/backend_local_profile.py").read_text(
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
        marker = "LOCAL_PROFILE_REPORT="
        line = next(
            (
                s[len(marker) :]
                for s in result.stdout.splitlines()
                if s.startswith(marker)
            ),
            None,
        )
        report = (
            json.loads(line)
            if line
            else {
                "status": "failed",
                "error_type": "MissingSanitizedChildReport",
                "returncode": result.returncode,
            }
        )
        report["readiness_seconds"] = ready_seconds
        write(REPORT / "live-profile.json", report)
        for row in report.get("cases", []):
            print(
                row["case_id"],
                row.get("attempt", {}).get("status"),
                row.get("attempt", {}).get("stage_error"),
                round(row["wall_seconds"], 2),
                flush=True,
            )
    except BaseException as exc:
        if not (REPORT / "live-profile.json").exists():
            write(
                REPORT / "live-profile.json",
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc).replace(key, "[REDACTED]"),
                },
            )
        raise
    finally:
        stop_service_and_wait(child)
        write(REPORT / "after-local-profile.json", system_snapshot())


if __name__ == "__main__":
    main()
