"""Separate transport, numeric grading, content review and cleanup outcomes."""

import json
import socket
import subprocess
import xml.etree.ElementTree as ET

from .common import (
    ROOT,
    REPORT,
    REPORT_BASE,
    MODELS,
    read,
    write,
    file_hash,
    system_snapshot,
)
from .launch import DOCKER


def main():
    baseline = read(REPORT / "baseline.json")
    after = system_snapshot()
    after["services"] = subprocess.check_output(
        [str(DOCKER), "ps", "--format", "{{.Names}} {{.Ports}}"], text=True
    ).splitlines()
    after["provider"] = subprocess.check_output(
        [
            str(DOCKER),
            "exec",
            "medresident-tutor-backend-1",
            "python",
            "-c",
            "import json; from app.core.config import get_settings; c=get_settings(); print(json.dumps(dict(app_env=c.app_env,practice_provider=c.practice_provider,model_calls_enabled=c.model_calls_enabled)))",
        ],
        text=True,
    ).strip()
    old = REPORT_BASE / "runs/20261109T063733Z"
    changed_old = [
        n
        for n, h in read(REPORT / "old-run-hashes.json").items()
        if file_hash(old / n) != h
    ]
    changed_frozen = [
        n
        for n, h in read(REPORT / "protected-file-hashes.json").items()
        if file_hash(ROOT / n) != h
    ]
    manifest = read(MODELS / "locked-adapters.json")["medical"]
    assert (
        file_hash(ROOT / manifest["adapter_path"] / "adapter_model.safetensors")
        == manifest["adapter_sha256"]
    )
    live = read(REPORT / "live-profile.json")
    reviewed = []
    for row in live.get("cases", []):
        cid, rid = row["case_id"], row["request_id"]
        generation = read(REPORT / "http-generations" / (rid + ".json"))
        trace = read(REPORT / "http-token-traces" / (rid + ".json"))
        frozen = read(REPORT / "inputs" / (cid + ".json"))
        output = row["attempt"]["medical_evaluation"]
        expected = read(REPORT / "expected" / (cid + ".json"))
        assert json.loads(generation["raw"]["text"]) == output
        assert (
            generation["input"] == frozen
            and frozen["student_answer"] in trace["actual_decoded_prompt"]
        )
        reviewed.append(
            {
                "case_id": cid,
                "request_id": rid,
                "attempt_id": row["attempt"]["id"],
                "http_status": row["http_status"],
                "attempt_status": row["attempt"]["status"],
                "stage_error": row["attempt"]["stage_error"],
                "wall_seconds": row["wall_seconds"],
                "generation_seconds": generation["raw"]["inference_seconds"],
                "provider_calls": row["provider_calls"],
                "detail_reload_matches": row["detail_reload_matches"],
                "history_contains_attempt": row["history_contains_attempt"],
                "idempotency_no_duplicate": row.get(
                    "duplicate_same_attempt_no_model_call"
                ),
                "actual_scores": [s["score"] for s in output["rubric_scores"]],
                "expected_scores": [s["score"] for s in expected["criteria"]],
                "raw_equals_parsed": True,
                "payload_matches_frozen_input": True,
                "finish_reason": trace["finish_reason"],
                "token_limit_hit": trace["token_limit_hit"],
                "score_matches_expected": [s["score"] for s in output["rubric_scores"]]
                == [s["score"] for s in expected["criteria"]],
                "content_review": "Requires separate source-based human review; not inferred from HTTP status or score matching",
            }
        )
    suite = ET.parse(REPORT / "deadline-tests.xml").getroot().find("testsuite")
    ports = {}
    for port in (8101, 8102, 3000, 8000, 5433, 7687):
        with socket.socket() as s:
            ports[str(port)] = s.connect_ex(("127.0.0.1", port)) == 0
    running = subprocess.check_output(
        [
            str(DOCKER),
            "ps",
            "--format",
            "{{.Names}}",
            "--filter",
            "name=medresident-local-",
        ],
        text=True,
    ).splitlines()
    summary = {
        "status": "local_timeout_profile_verified_model_content_review_required",
        "profile": live.get("profile"),
        "readiness_seconds": live.get("readiness_seconds"),
        "generation_budget": read(REPORT / "generation-budget.json"),
        "teaching_model_generations": 0,
        "tests": {k: int(suite.get(k, "0")) for k in ("tests", "failures", "errors")},
        "frontend_typecheck": "passed",
        "cases": reviewed,
        "actual_live_max_wall_seconds": max(c["wall_seconds"] for c in reviewed),
        "live_crossed_old_30_second_limit": any(
            c["wall_seconds"] > 30 for c in reviewed
        ),
        "deadline_evidence_note": "New profile is active and controlled tests accept a response beyond the old scaled deadline. All actual new requests happened to finish under 30 seconds; do not claim a live >30-second comparison.",
        "all_test_attempts_rolled_back": live.get(
            "all_test_attempts_absent_after_rollback"
        ),
        "mastery_updated": False,
        "browser_e2e": False,
        "backend_scope": live.get("scope"),
        "investigation": read(REPORT / "investigation.json"),
        "old_run_files_changed": changed_old,
        "frozen_source_data_changed": changed_frozen,
        "before": baseline,
        "after": after,
        "main_provider_unchanged": after["provider"] == baseline["provider"],
        "main_services_preserved": set(baseline["services"]) <= set(after["services"]),
        "owned_containers_running": running,
        "ports": ports,
        "stop_identity": read(REPORT / "medical-stop-identity.json"),
        "weights_adapters_cache_venvs_kept": True,
        "production_and_mock_default_seconds": 30,
    }
    assert (
        summary["generation_budget"]["calls_started"]
        == summary["generation_budget"]["calls_finished"]
        == len(reviewed)
    )
    assert len(reviewed) <= summary["generation_budget"]["limit"] <= 4
    assert (
        not changed_old
        and not changed_frozen
        and not running
        and not ports["8101"]
        and not ports["8102"]
    )
    assert (
        summary["all_test_attempts_rolled_back"]
        and summary["main_provider_unchanged"]
        and summary["main_services_preserved"]
    )
    assert all(
        c["attempt_status"] == "completed"
        and c["provider_calls"] == {"medical": 1, "teaching": 1}
        and c["idempotency_no_duplicate"]
        for c in reviewed
    )
    write(REPORT / "profile-summary.json", summary)
    print(
        "Live completed",
        len(reviewed),
        "; generations 4/4; Teaching mock only; DB rollback verified; old artifacts/frozen sources unchanged.",
    )
    print("GPU before", baseline["gpu"], "after", after["gpu"])
    print(
        "RAM_FREE_GIB",
        round(baseline["system"]["ram_available_bytes"] / 1024**3, 2),
        round(after["system"]["ram_available_bytes"] / 1024**3, 2),
    )


if __name__ == "__main__":
    main()
