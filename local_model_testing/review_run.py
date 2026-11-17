"""Report the observed local run; never changes model output, prompts or gold."""

import socket
import subprocess
import statistics

from .common import ROOT, REPORT, read, write, file_hash, system_snapshot
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
    hashes = read(REPORT / "protected-file-hashes.json")
    changed = [
        name for name, digest in hashes.items() if file_hash(ROOT / name) != digest
    ]
    medical = read(REPORT / "medical-batch.json")
    teaching = read(REPORT / "teaching-batch.json")
    mc = [c for c in medical["cases"] if c.get("execution") == "local_real_adapter"]
    tc = teaching.get("cases", [])
    notes = read(REPORT / "manual-review-notes.json")
    assert file_hash(REPORT / "medical-batch.json") == notes["medical_batch_sha256"], (
        "Review notes belong to a different model output"
    )
    findings = notes["findings"]
    medical_review = []
    for row in mc:
        cid = row["case_id"]
        expected = read(REPORT / "expected" / (cid + ".json"))
        medical_review.append(
            {
                "case_id": cid,
                "contract_valid": row["contract_valid"],
                "expected_scores": [c["score"] for c in expected["criteria"]],
                "actual_scores": [
                    c["score"] for c in row["prediction"]["rubric_scores"]
                ],
                "frozen_score_match": row["expected_score_match"],
                "source_based_manual_findings": findings.get(cid, []),
                "manual_review_scope": "Assistant checks against fixed source/rubric/expected policy; not clinical expert approval",
            }
        )
    write(REPORT / "medical-manual-review.json", medical_review)
    http = read(REPORT / "practice-http.json")
    generation = read(REPORT / "medical-http-generation.json")
    replay = (
        read(REPORT / "practice-replay.json")
        if (REPORT / "practice-replay.json").exists()
        else {"completed": False, "status": "not_run"}
    )
    rejected = read(REPORT / "practice-replay-CLINICAL_DEMO_V1_CASE01__incorrect.json")
    expected_rejection = (
        rejected.get("attempt", {}).get("status") == "teaching_failed"
        and rejected.get("attempt", {}).get("stage_error", {}).get("code")
        == "TEACHING_ALIGNMENT_INVALID"
    )
    ports = {}
    for port in (8101, 8102, 3000, 8000, 5433, 7687):
        with socket.socket() as sock:
            ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
    containers = subprocess.check_output(
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
        "status": "local_inference_executed_quality_and_live_http_issues_found",
        "adapter_inspection": read(REPORT / "adapter-inspection.json"),
        "medical": {
            "batch_cases": len(mc),
            "smoke_generations": 1,
            "http_generations": 1,
            "total_real_generations": len(mc) + 2,
            "schema_valid_cases": sum(bool(c["contract_valid"]) for c in mc),
            "frozen_score_matching_cases": sum(
                bool(c["expected_score_match"]) for c in mc
            ),
            "manual_content_flags_cases": len(findings),
            "clinical_expert_approved": False,
            "average_batch_generation_seconds": statistics.mean(
                c["inference_seconds"] for c in mc
            ),
            "peak_torch_allocated_bytes": medical["peak_vram_allocated_bytes"],
            "grading_ready_for_official_use": False,
        },
        "teaching": {
            "batch_inputs": len(tc),
            "smoke_generations": 1 if "smoke" in teaching else 0,
            "status": teaching.get("status"),
            "error": teaching.get("error"),
            "raw_contract_valid_cases": sum(
                bool(c.get("raw_metrics", {}).get("contract_valid")) for c in tc
            ),
            "guarded_rule_checks_all_pass_cases": sum(
                bool(c.get("guard_metrics"))
                and all(c["guard_metrics"].values())
                and not c["guard_errors"]
                for c in tc
            ),
            "peak_torch_allocated_bytes": teaching.get("peak_vram_allocated_bytes"),
            "upstream_medical_errors_kept": True,
            "feedback_clinical_accuracy_not_established": True,
        },
        "live_backend_http": {
            "medical_ready_http": http.get("medical_ready_http"),
            "practice_submit_http": http.get("submit_http"),
            "attempt_status": http.get("attempt", {}).get("status"),
            "stage_error": http.get("attempt", {}).get("stage_error"),
            "model_completed_after_seconds": generation["raw"]["inference_seconds"],
            "teaching_mock_calls": http.get("provider_calls", {}).get("teaching"),
            "test_writes_rolled_back": http.get("test_attempt_absent_after_rollback"),
        },
        "backend_replay": {
            "completed": replay.get("completed"),
            "test_writes_rolled_back": replay.get("test_attempt_absent_after_rollback"),
            "both_stages": "saved real local outputs replayed; no live service/model call",
            "new_model_calls": 0,
            "invalid_teaching_rejected": expected_rejection,
            "rejected_case_writes_rolled_back": rejected.get(
                "test_attempt_absent_after_rollback"
            ),
        },
        "browser_FE_model_e2e": "not_run; main web provider kept mock",
        "app_preflight": read(REPORT / "app-preflight.json"),
        "before": baseline,
        "after": after,
        "provider_unchanged": baseline["provider"] == after["provider"],
        "original_services_preserved": set(baseline["services"])
        <= set(after["services"]),
        "protected_files_checked": len(hashes),
        "protected_files_changed": changed,
        "owned_containers_running": containers,
        "ports": ports,
        "automatic_model_retries": 0,
        "mastery_updated": False,
        "weights_adapters_venvs_preserved": True,
    }
    assert (
        not changed
        and summary["provider_unchanged"]
        and summary["original_services_preserved"]
    )
    assert not containers and not ports["8101"] and not ports["8102"]
    assert (
        not (REPORT / "owned-worker.json").exists()
        and not (REPORT / "worker-container.cid").exists()
    )
    write(REPORT / "run-summary.json", summary)
    print(
        "Medical score matches",
        summary["medical"]["frozen_score_matching_cases"],
        "/",
        len(mc),
        "; manual content flags",
        len(findings),
    )
    print(
        "Teaching guarded rule checks",
        summary["teaching"]["guarded_rule_checks_all_pass_cases"],
        "/",
        len(tc),
    )
    print(
        "BE replay completed",
        replay.get("completed"),
        "; no owned containers remain; protected files unchanged",
        len(hashes),
    )
    print("GPU before", baseline["gpu"], "; after", after["gpu"])
    print(
        "RAM_AVAILABLE_GIB_BEFORE_AFTER",
        round(baseline["system"]["ram_available_bytes"] / 1024**3, 2),
        round(after["system"]["ram_available_bytes"] / 1024**3, 2),
    )


if __name__ == "__main__":
    main()
