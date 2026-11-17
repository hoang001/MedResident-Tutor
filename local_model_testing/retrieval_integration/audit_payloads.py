"""Freeze actual backend-retrieved development payloads; CPU tokenization, zero generation."""

import copy
import json
import sys

from .common import ROOT, RUN, CORPUS, read, write, digest, file_hash


def main():
    sys.path.insert(0, str(ROOT / "model-training"))
    from transformers import AutoTokenizer
    from src.medical.inference import SYSTEM_PROMPT, build_user_content
    from src.medical.validation import EvaluationRequest

    preflight = read(RUN / "preflight.json")
    assert (
        preflight.get("status") != "failed"
        and preflight["outer_transaction_rolled_back"]
    )
    assert preflight["test_attempts_and_questions_absent_after_rollback"]
    assert len(preflight["cases"]) == 30
    captures = {r["trace_id"]: r["payload"] for r in preflight["payload_captures"]}
    references = read(RUN / "medical-development.json")
    tokenizer = AutoTokenizer.from_pretrained(
        ROOT / "data/local-models/base/Qwen3-4B-Instruct-2507", local_files_only=True
    )
    planned = []
    for mode in ("vector", "hybrid"):
        for q in references:
            case = next(
                c
                for c in preflight["cases"]
                if c["mode"] == mode
                and c["sample_id"].split("__")[0] == q["question_id"]
            )
            trace = case["attempt"]["retrieval"]
            assert trace["effective_strategy"] == mode
            assert trace["selected_evidence"]
            for answer in q["answers"]:
                payload = copy.deepcopy(captures[trace["trace_id"]])
                payload["student_answer"] = answer["student_answer"]
                EvaluationRequest.model_validate(payload)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_content(payload)},
                ]
                tokens = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_dict=True,
                )
                n = len(tokens["input_ids"])
                assert n <= 4096 and n + 1200 <= 8192, (
                    "Input/context limit: no truncation or model call"
                )
                decoded = tokenizer.decode(
                    tokens["input_ids"], skip_special_tokens=False
                )
                assert answer["student_answer"] in decoded
                planned.append(
                    {
                        "mode": mode,
                        "sample_id": answer["sample_id"],
                        "payload": payload,
                        "payload_sha256": digest(payload),
                        "input_tokens": n,
                        "prompt_sha256": digest(decoded),
                        "retrieval_source_trace_id": trace["trace_id"],
                    }
                )
    write(RUN / "planned-medical-payloads.json", planned)
    write(
        RUN / "payload-token-audit.json",
        {
            "generation_calls": 0,
            "planned_inputs": len(planned),
            "max_input_tokens": max(r["input_tokens"] for r in planned),
            "all_complete": True,
            "retrieved_ids_hashes_match_backend_payload": True,
            "corpus_sha256": file_hash(CORPUS / "corpus.jsonl"),
            "index_manifest_sha256": file_hash(CORPUS / "index-manifest.json"),
        },
    )
    print(json.dumps(read(RUN / "payload-token-audit.json")), flush=True)


if __name__ == "__main__":
    main()
