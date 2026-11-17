"""Offline trace reconstruction. Tokenizer only; never loads/generates a model."""

import hashlib
import json
import sys

from .common import ROOT, REPORT, REPORT_BASE, read, write, file_hash

sys.path.insert(0, str(ROOT / "model-training"))
from src.medical.inference import SYSTEM_PROMPT, build_user_content
from src.medical.validation import EvaluationRequest, validate_output


def main():
    from transformers import AutoTokenizer

    old = REPORT_BASE / "runs/20261109T063733Z"
    batch = read(old / "medical-batch.json")
    notes = read(old / "manual-review-notes.json")
    assert file_hash(old / "medical-batch.json") == notes["medical_batch_sha256"]
    metadata = batch["readiness"]["metadata"]
    assert (
        hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
        == metadata["system_prompt_sha256"]
    )
    tokenizer = AutoTokenizer.from_pretrained(
        ROOT / "data/local-models/base/Qwen3-4B-Instruct-2507", local_files_only=True
    )
    assert (
        hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
        == metadata["chat_template_sha256"]
    )
    manifest = read(old / "integration-inputs.json")
    explanations = {
        "CLINICAL_DEMO_V1_CASE01__incorrect": {
            "classification": "model_completion_semantic_error_after_plumbing_checks",
            "expected_clear": True,
            "analysis": "Source explicitly says distal radius and intra-articular. Student claims distal ulna and no articular involvement. Awarding radius credit and treating both as correct contradicts these supplied facts; parser retains this error.",
        },
        "CLINICAL_DEMO_V1_XR01__incorrect": {
            "classification": "model_completion_semantic_inconsistency_after_plumbing_checks",
            "expected_clear": True,
            "analysis": "Annotation states fracture and grid row 2/column 2. Student denies fracture and gives row 1/column 1. Zero total matches but a positive fracture correct_point contradicts the answer; the wrong grid claim is treated as absent rather than addressed.",
        },
        "CLINICAL_DEMO_V1_XR01__unrelated": {
            "classification": "expected_policy_ambiguity_and_unverifiable_nonclinical_claim_classification",
            "expected_clear": False,
            "analysis": "Zero score and two missing criteria are unambiguous. Whether an off-topic sentence also belongs in incorrect_points is less explicit in rubric; prompt restricts this to false claims and says not to infer falsity without evidence. Music preference cannot be verified from XR evidence. Keep frozen expected; propose clarifying off-topic-vs-factual-error policy separately, not a keyword patch.",
        },
    }
    rows = []
    for cid, explanation in explanations.items():
        entry = next(c for c in manifest["cases"] if c["case_id"] == cid)
        path, expected_path = (
            old / "inputs" / (cid + ".json"),
            old / "expected" / (cid + ".json"),
        )
        assert (
            file_hash(path) == entry["input_sha256"]
            and file_hash(expected_path) == entry["expected_sha256"]
        )
        payload, expected = read(path), read(expected_path)
        record = next(c for c in batch["cases"] if c["case_id"] == cid)
        raw_file = read(old / "raw" / (cid + ".json"))
        assert raw_file["text"] == record["text"]
        parsed = validate_output(
            record["text"], EvaluationRequest.model_validate(payload)
        )
        assert parsed == record["prediction"] == json.loads(record["text"])
        mapped = json.loads(build_user_content(payload))
        assert mapped == payload
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_content(payload)},
        ]
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        ids = tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True
        )
        assert len(ids) == record["input_tokens"]
        trace = {
            "case_id": cid,
            "question_identity": {
                "exercise_id": entry["question_id"],
                "version_basis": "frozen input SHA-256; no separate question revision field",
                "input_sha256": entry["input_sha256"],
            },
            "input": payload,
            "payload_after_mapping": mapped,
            "messages": messages,
            "rendered_chat_template": rendered,
            "rendered_chat_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            "input_token_ids_sha256": hashlib.sha256(
                json.dumps(ids).encode()
            ).hexdigest(),
            "input_tokens_reconstructed": len(ids),
            "input_tokens_recorded": record["input_tokens"],
            "raw_completion": record["text"],
            "parsed_output": parsed,
            "expected": expected,
            "generated_tokens": record["generated_tokens"],
            "max_new_tokens": 1200,
            "token_limit_hit": record["generated_tokens"] >= 1200,
            "stop_reason": "not captured in old run; output below token cap; do not assert EOS without original token IDs",
            "no_input_truncation_evidence": len(ids) <= 4096
            and len(ids) + 1200 <= 8192,
            "mapping_parser_checks": "answer/rubric/evidence exact; frozen hashes/token count/template hash match; raw JSON equals parsed output; no prediction cache in runner",
            "reconstruction_limit": "Old run did not persist actual rendered prompt bytes/token IDs or EOS; reconstructed from frozen input and unchanged implementation, supported by matching recorded token counts/hashes",
            **explanation,
        }
        write(REPORT / "investigation" / (cid + ".json"), trace)
        rows.append(
            {
                k: trace[k]
                for k in (
                    "case_id",
                    "classification",
                    "expected_clear",
                    "analysis",
                    "input_tokens_reconstructed",
                    "generated_tokens",
                    "token_limit_hit",
                )
            }
        )
    teacher = read(old / "teaching-batch.json")
    tc = next(c for c in teacher["cases"] if c["case_id"].endswith("CASE01__incorrect"))
    ti = next(
        c
        for c in read(old / "teaching-replay-inputs.json")
        if c["case_id"] == tc["case_id"]
    )
    med = next(c for c in batch["cases"] if c["case_id"] == tc["case_id"])
    assert ti["input"]["medical_evaluation"] == med["prediction"]
    write(
        REPORT / "investigation.json",
        {
            "inference_calls": 0,
            "old_review_hash_verified": True,
            "cases": rows,
            "tokenizer_and_prompt_hash_match_old_runtime": True,
            "xr_evidence_scope": "Text describes original fracture annotation and derived 3x3 grid; supports only requested fracture/grid criteria, not treatment/anatomical subtype. Model receives text, not pixels.",
            "validator_scope": "Existing checks: exact criterion IDs/order/no duplicates, bounded scores, summed total, refs subset, strict JSON/schema. No semantic grading or point-list-vs-score truth test; these errors therefore legitimately pass numeric contract.",
            "teaching_old_only": {
                "medical_input_equals_original_output": True,
                "guard_errors": tc["guard_errors"],
                "analysis": "Medical lists both claims as correct while second criterion score is zero. Teaching moves no-articular-involvement to corrections/missing contrary to those lists. Confounded by contradictory upstream evaluation; these artifacts do not establish an independent Teaching defect on consistent input. No Teaching call or edited Medical evaluation.",
            },
            "proposal_only": "Specify off-topic policy and general evidence/answer/criterion consistency requirements using an expert-reviewed independent dataset. Do not auto-rewrite scores, add anatomy keyword rules, or treat lexical similarity as clinical adjudication.",
        },
    )
    print(
        "Offline investigation complete: 3 reconstructed traces; 0 model generations; old raw/expected unchanged."
    )


if __name__ == "__main__":
    main()
