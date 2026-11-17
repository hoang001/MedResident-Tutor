"""CPU tokenizer audit/reconstruction, no model weights loaded and no generate calls."""
import gc
import hashlib
import json

from local_model_testing.common import KINDS, MODELS

from .common import DATA, RUN, fingerprint, rows, read, write
from .worker import messages


def main():
    from transformers import AutoTokenizer

    result = {}
    for kind in ("medical", "teaching"):
        tokenizer = AutoTokenizer.from_pretrained(MODELS / "base" / KINDS[kind]["name"], local_files_only=True)
        records, mismatches = [], []
        checked = {kind+"_base": 0, kind+"_adapter": 0}
        no_recorded_prompt = []
        for row in rows(DATA / (kind+"-inputs.jsonl")):
            chat = messages(kind, row["payload"])
            inputs = tokenizer.apply_chat_template(chat, tokenize=True, add_generation_prompt=True,
                                                   return_dict=True)
            decoded = tokenizer.decode(inputs["input_ids"], skip_special_tokens=False)
            sha = fingerprint(decoded)
            n = len(inputs["input_ids"])
            assert n <= 4096 and n + (1200 if kind == "medical" else 1600) <= 8192
            # Input is source/question/rubric + actual answer, never expected-label object.
            assert row["payload"]["student_answer"] in decoded
            for config in (kind+"_base", kind+"_adapter"):
                checkpoint = RUN / config / (row["sample_id"]+".json")
                if checkpoint.exists():
                    item = read(checkpoint)
                    if not item.get("actual_prompt_sha256"):
                        no_recorded_prompt.append({"config": config, "sample_id": row["sample_id"],
                                                   "error": item.get("error")})
                        continue
                    checked[config] += 1
                    if item["actual_prompt_sha256"] != sha:
                        mismatches.append({"config": config, "sample_id": row["sample_id"]})
            records.append({"sample_id": row["sample_id"], "input_tokens": n, "actual_prompt_sha256": sha})
            if row["sample_id"] in {"MRB1_03_01__full", "MRB1_04_01__full"}:
                write(RUN / "prompt-audit" / (row["sample_id"]+".json"),
                      {"messages": chat, "decoded_prompt": decoded, "sha256_canonical_json": sha,
                       "generation_calls": 0})
        result[kind] = {"inputs": len(records), "max_input_tokens": max(r["input_tokens"] for r in records),
                        "prompt_mismatches": mismatches,
                        "actual_checkpoint_prompts_checked": checked,
                        "checkpoints_without_recorded_prompt": no_recorded_prompt,
                        "system_prompt_sha256_utf8": hashlib.sha256(messages(kind, rows(DATA/(kind+"-inputs.jsonl"))[0]["payload"])[0]["content"].encode()).hexdigest(),
                        "records": records}
        tokenizer = None
        gc.collect()
    write(RUN / "token-payload-audit.json", {"generation_calls": 0, "audit": result})
    assert not any(r["prompt_mismatches"] for r in result.values())
    print(json.dumps({k: {field: v[field] for field in ("inputs", "max_input_tokens", "prompt_mismatches",
                                                     "actual_checkpoint_prompts_checked",
                                                     "checkpoints_without_recorded_prompt")}
                      for k, v in result.items()}))


if __name__ == "__main__":
    main()
