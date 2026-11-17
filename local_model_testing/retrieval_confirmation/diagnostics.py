"""Post-run raw validation and deterministic mock reproduction; no inference."""

import asyncio
from collections import Counter

from app.modules.practice.providers import MockProvider
from app.modules.practice.service import teaching_payload
from src.teaching.apply_teaching_guards import apply_teaching_guards
from src.teaching.validate_dataset import prediction_metrics
from local_model_testing.experiment.worker import parse
from .common import RUN, read, write, digest


async def main():
    refs = {
        a["sample_id"]: a["expected_vector"]
        for q in read(RUN / "medical-development.json")
        for a in q["answers"]
    }
    rows = []
    for case in read(RUN / "live.json")["cases"]:
        result = case["attempt"]
        trace = result["retrieval"]
        tid = trace["trace_id"]
        request = read(RUN / "requests" / (tid + ".json"))
        raw = read(RUN / "raw" / (tid + ".json"))
        server = read(RUN / "server-inputs" / (tid + ".json"))
        tokens = read(RUN / "token-traces" / (tid + ".json"))
        validated = parse("medical", request["payload"], raw["raw"]["text"])
        assert validated["schema_valid"] and validated["contract_valid"]
        assert validated["parsed"] == result["medical_evaluation"]
        assert (
            server["input_payload_sha256"]
            == request["payload_sha256"]
            == digest(request["payload"])
        )
        assert (
            server["evidence_at_http_server"]
            == trace["selected_evidence"]
            == raw["evidence_at_http_server"]
        )
        medical = validated["parsed"]
        overlap = sorted(
            set(medical["incorrect_points"]) & set(medical["missing_points"])
        )
        vector = [c["score"] for c in medical["rubric_scores"]]
        row = {
            "sample_id": case["sample_id"],
            "mode": case["mode"],
            "trace_id": tid,
            "ledger_id": request["attempt_id"],
            "expected_vector": refs[case["sample_id"]],
            "observed_vector": vector,
            "score_vector_matches": vector == refs[case["sample_id"]],
            "incorrect_missing_exact_overlap": overlap,
            "schema_and_contract_revalidated": True,
            "raw_equals_api_medical_evaluation": True,
            "server_evidence_chain_verified": True,
            "actual_prompt_contains_student_answer_once": tokens[
                "actual_decoded_prompt"
            ].count(request["payload"]["student_answer"])
            == 1,
            "input_tokens": tokens["input_tokens"],
            "generated_tokens": tokens["generated_tokens"],
            "truncated": tokens["truncated"],
            "student_answer": request["payload"]["student_answer"],
            "rubric": request["payload"]["rubric"],
            "evidence": request["payload"]["evidence"],
            "parsed": medical,
            "api_status": result["status"],
        }
        if result["status"] == "teaching_failed":
            teaching_input = teaching_payload(request["payload"], medical)
            mock, _ = await MockProvider().evaluate("teaching", teaching_input)
            guarded = apply_teaching_guards(teaching_input, mock)
            metrics, errors = prediction_metrics(teaching_input, guarded)
            assert errors
            row["offline_mock_diagnostic"] = {
                "execution": "deterministic reproduction after run; not a new API/model result",
                "metrics": metrics,
                "errors": errors,
                "mock_learning_priority": mock["learning_priority"],
            }
        rows.append(row)
    summary = {
        "reviewer": "Codex source/prompt/raw comparison, not clinician adjudication",
        "no_model_calls": True,
        "references_unchanged": True,
        "rows": rows,
        "score_vector_mismatches": sum(not r["score_vector_matches"] for r in rows),
        "score_matches_with_incorrect_missing_overlap": sum(
            r["score_vector_matches"] and bool(r["incorrect_missing_exact_overlap"])
            for r in rows
        ),
        "teaching_mock_diagnostic_errors": dict(
            Counter(
                e
                for r in rows
                for e in r.get("offline_mock_diagnostic", {}).get("errors", [])
            )
        ),
    }
    write(RUN / "content-analysis.json", summary)
    print({k: v for k, v in summary.items() if k not in {"rows", "reviewer"}})


if __name__ == "__main__":
    asyncio.run(main())
