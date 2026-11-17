"""One model per owned process; exit/unload on every success or failure path.

This is standalone local batch inference, not backend HTTP E2E.
"""

import argparse
import copy
import os
import secrets
import subprocess
import sys

import psutil

from .common import ROOT, REPORT, file_hash, read, write, system_snapshot
from .artifacts import check
from .process_control import claim, release

sys.path[:0] = [str(ROOT / "model-training"), str(ROOT / "services/medical")]


def check_capacity(kind):
    if psutil.virtual_memory().available < 4 * 1024**3:
        raise RuntimeError(
            "AVAILABLE_RUNTIME_RAM_BELOW_4_GIB; stop rather than attempt OOM"
        )
    free = int(
        subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True,
        )
        .strip()
        .splitlines()[0]
    )
    if free < {"medical": 4096, "teaching": 6144}[kind]:
        raise RuntimeError("INSUFFICIENT_FREE_VRAM_FOR_SELECTED_MODEL")
    apps = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=process_name", "--format=csv,noheader"],
        text=True,
    ).casefold()
    if any(
        name in apps
        for name in ("python", "ollama", "vllm", "llama-server", "lmstudio")
    ):
        raise RuntimeError(
            "EXISTING_GPU_MODEL_OR_PYTHON_PROCESS; refusing concurrent model load"
        )


def medical_inputs():
    manifest = read(REPORT / "integration-inputs.json")
    assert len(manifest["cases"]) == 10
    for case in manifest["cases"]:
        path = REPORT / "inputs" / (case["case_id"] + ".json")
        expected_path = REPORT / "expected" / (case["case_id"] + ".json")
        if (
            file_hash(path) != case["input_sha256"]
            or file_hash(expected_path) != case["expected_sha256"]
        ):
            raise ValueError("FROZEN_INTEGRATION_INPUT_OR_EXPECTATION_CHANGED")
        yield case["case_id"], read(path), read(expected_path)


def teaching_inputs():
    # Only saved, contract-valid real Medical output is eligible for replay.
    medical = read(REPORT / "medical-batch.json")
    saved = {
        c["case_id"]: c
        for c in medical["cases"]
        if c.get("contract_valid") and c.get("execution") == "local_real_adapter"
    }
    chosen = ["CASE01__full", "CASE01__incorrect", "XR01__partial", "XR01__full"]
    items = []
    for short in chosen:
        cid = "CLINICAL_DEMO_V1_" + short
        row = saved[cid]
        payload = read(REPORT / "inputs" / (cid + ".json"))
        payload = {
            "schema_version": "1.0.0",
            "question": payload["question"],
            "student_answer": payload["student_answer"],
            "medical_evaluation": copy.deepcopy(row["prediction"]),
            "learner_context": {
                "mastery": [],
                "recurring_errors": [],
                "recent_improvements": [],
                "recent_attempts_summary": None,
            },
            "metadata": {
                "question_id": cid.split("__")[0],
                "course_id": None,
                "course_name": None,
                "topic_id": None,
                "topic_name": None,
                "specialty": None,
                "course_group": None,
                "specialty_level": None,
                "concept_ids": [],
            },
        }
        items.append(
            (cid, payload, {"origin": "saved_real_medical_output", "source_case": cid})
        )
    context_item = next(
        (
            item
            for item in items
            if item[1]["medical_evaluation"]["incorrect_points"]
            or item[1]["medical_evaluation"]["missing_points"]
        ),
        None,
    )
    context = copy.deepcopy(context_item[1] if context_item else items[1][1])
    anchors = (
        context["medical_evaluation"]["incorrect_points"]
        or context["medical_evaluation"]["missing_points"]
    )
    if anchors:
        context["learner_context"]["recurring_errors"] = [
            {"error_summary": anchors[0], "count": 2}
        ]
        items.append(
            (
                "context_fixture",
                context,
                {
                    "origin": "real_medical_plus_synthetic_learner_context_fixture",
                    "history_is_fixture": True,
                    "source_case": context_item[0] if context_item else items[1][0],
                },
            )
        )
    insufficient = copy.deepcopy(items[2][1])
    insufficient["medical_evaluation"]["sufficient_evidence"] = False
    items.append(
        (
            "insufficient_fixture",
            insufficient,
            {
                "origin": "manual_fixture_modified_from_saved_medical",
                "medical_sufficient_evidence_modified_for_guard_test": True,
            },
        )
    )
    prepared = [{"case_id": cid, "input": p, **meta} for cid, p, meta in items]
    prepared_path = REPORT / "teaching-replay-inputs.json"
    if prepared_path.exists():
        if read(prepared_path) != prepared:
            raise ValueError("FROZEN_TEACHING_REPLAY_INPUT_CHANGED")
    else:
        write(prepared_path, prepared)
    from src.teaching.validate_dataset import input_errors

    for cid, payload, _ in items:
        errors = input_errors(payload)
        if errors:
            raise ValueError(
                "TEACHING_REPLAY_INPUT_INVALID: " + cid + "; " + "; ".join(errors)
            )
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["medical", "teaching"])
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Medical HTTP stage only; no batch generation",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="One generation only; without this, smoke then bounded batch",
    )
    args = parser.parse_args()
    state = claim(args.kind)
    runner = None
    torch = None
    report = {
        "kind": args.kind,
        "status": "starting",
        "pid": os.getpid(),
        "cases": [],
        "backend_http_e2e": "not_run",
        "mastery_updated": False,
        "retry_count": 0,
    }
    destination = REPORT / (
        args.kind
        + (
            "-http-service.json"
            if args.serve
            else "-smoke.json"
            if args.smoke
            else "-batch.json"
        )
    )
    if destination.exists():
        release(state)
        raise FileExistsError("Refusing to overwrite an earlier model run/report")
    try:
        report["before"] = system_snapshot()
        base, adapter, identity = check(
            args.kind
        )  # Missing adapters fail before any GPU import/load.
        report["artifact_identity"] = identity
        check_capacity(args.kind)
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
        )
        import torch

        torch.cuda.reset_peak_memory_stats()
        if args.kind == "medical":
            from medical_service.config import Settings
            from medical_service.runner import PilotRunner
            from medical_service.validation import validate_output, ServiceError

            settings = Settings(
                base_path=base,
                adapter_path=adapter,
                adapter_sha256=identity["adapter_sha256"],
                adapter_config_sha256=identity["adapter_config_sha256"],
                base_config_sha256=identity["base_config_sha256"],
                api_key=os.environ["MEDICAL_API_KEY"]
                if args.serve
                else secrets.token_urlsafe(32),
            )
            # Settings key is ephemeral/unused: batch runner has no HTTP listener or remote call.
            runner = PilotRunner(settings)
            inputs = list(medical_inputs())
        else:
            from .teaching import TeachingRunner

            runner = TeachingRunner(base, adapter, identity)
            inputs = teaching_inputs()
        runner.load()
        # Recheck artifact identity after loading, as service readiness does.
        check(args.kind)
        report["readiness"] = {
            "artifacts_verified": True,
            "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0),
            "metadata": runner.metadata,
            "scope": "batch runner, not HTTP /ready endpoint",
        }
        if args.serve:
            if args.kind != "medical":
                raise ValueError("HTTP_STAGE_IS_MEDICAL_ONLY")
            from .http_service import serve

            report["status"] = "serving_existing_medical_api"
            write(destination, report)
            serve(runner, settings)
            report["status"] = "http_service_stopped"
            return
        smoke = next(item for item in inputs if item[1]["student_answer"].strip())
        smoke_output = runner.generate(smoke[1])
        if args.kind == "medical":
            request = __import__(
                "src.medical.validation", fromlist=["EvaluationRequest"]
            ).EvaluationRequest.model_validate(smoke[1])
            # Keep raw output even if contract validation fails.
            write(REPORT / "medical-smoke-raw.json", vars(smoke_output))
            report["smoke"] = {
                "prediction": validate_output(smoke_output.text, request),
                **vars(smoke_output),
            }
        else:
            write(REPORT / "teaching-smoke-raw.json", smoke_output)
            report["smoke"] = smoke_output
            if smoke_output["guard_errors"] or not all(
                smoke_output["guard_metrics"].values()
            ):
                raise RuntimeError("TEACHING_SMOKE_CONTRACT_OR_GUARD_FAILED")
        if not args.smoke:
            for cid, payload, expected in inputs:
                if not payload["student_answer"].strip():
                    report["cases"].append(
                        {
                            "case_id": cid,
                            "model_call": False,
                            "status": "app_rejection_check_required_separately_not_inferred",
                        }
                    )
                    continue
                result = {
                    "case_id": cid,
                    "execution": "local_real_adapter",
                    "input_origin": expected.get(
                        "origin", "new_manual_integration_answer"
                    ),
                }
                generated = runner.generate(payload)  # Exactly once. No auto retry.
                if args.kind == "medical":
                    result.update(vars(generated))
                    write(REPORT / "raw" / (cid + ".json"), result)
                    try:
                        from src.medical.validation import EvaluationRequest

                        prediction = validate_output(
                            generated.text, EvaluationRequest.model_validate(payload)
                        )
                        scores = {
                            c["criterion_id"]: c["score"]
                            for c in prediction["rubric_scores"]
                        }
                        result.update(
                            contract_valid=True,
                            prediction=prediction,
                            expected_score_match=all(
                                scores[c["criterion_id"]] == c["score"]
                                for c in expected["criteria"]
                            ),
                            expected_sufficient_evidence_match=prediction[
                                "sufficient_evidence"
                            ]
                            == expected["sufficient_evidence"],
                            semantic_point_review="required; score matching alone is not clinical PASS",
                        )
                    except ServiceError as exc:
                        result.update(
                            contract_valid=False,
                            error_code=exc.code,
                            http_equivalent=exc.status,
                        )
                else:
                    # Raw and guarded predictions are distinct fields and files.
                    result.update(generated, source=expected)
                    write(
                        REPORT / "teaching-raw" / (cid + ".json"),
                        {
                            "raw_text": generated["raw_text"],
                            "prediction": generated["raw_prediction"],
                        },
                    )
                    write(
                        REPORT / "teaching-guarded" / (cid + ".json"),
                        {
                            "prediction": generated["guarded_prediction"],
                            "metrics": generated["guard_metrics"],
                            "errors": generated["guard_errors"],
                        },
                    )
                report["cases"].append(result)
                write(destination, report)
                print(args.kind, cid, "recorded; manual review required", flush=True)
        report["status"] = "generations_finished_review_required"
    except Exception as exc:
        report["status"] = "blocked_or_failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(args.kind, report["status"], report["error"], flush=True)
        raise SystemExit(1) from None
    finally:
        try:
            if torch is not None and torch.cuda.is_initialized():
                report["peak_vram_allocated_bytes"] = torch.cuda.max_memory_allocated()
            if runner is not None:
                runner.close()
            if torch is not None and torch.cuda.is_initialized():
                torch.cuda.empty_cache()
        finally:
            report["cleanup"] = (
                "runner closed; process exit/container removal required to release CUDA context"
            )
            write(destination, report)
            release(state)


if __name__ == "__main__":
    main()
