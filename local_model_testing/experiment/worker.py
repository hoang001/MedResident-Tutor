"""Sequential local inference. Immutable V1 prompts/guards and exact frozen inputs."""
import argparse
import gc
import importlib.metadata
import json
import os
import shutil
import sys
import threading
import time

from local_model_testing.artifacts import check
from local_model_testing.common import system_snapshot
from local_model_testing.worker import check_capacity

from . import ledger
from .common import DATA, ROOT, RUN, file_hash, fingerprint, frozen, read, rows, write

sys.path.insert(0, str(ROOT / "model-training"))


def messages(kind, payload):
    if kind == "medical":
        from src.medical.inference import SYSTEM_PROMPT, build_user_content
        return [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_content(payload)}]
    from src.teaching.prepare_dataset import SYSTEM_PROMPT
    content = {k: payload[k] for k in (
        "question", "student_answer", "medical_evaluation", "learner_context", "metadata")}
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(content, ensure_ascii=False)}]


def parse(kind, payload, raw):
    if kind == "medical":
        from src.medical.inference import extract_json
        from src.medical.validation import (
            EvaluationRequest, MedicalEvaluation, ServiceError, strict_json, validate_output,
        )
        prediction, schema_valid, error = None, False, None
        try:
            prediction, parse_error = extract_json(raw, loads=strict_json)
            if parse_error or prediction is None:
                raise ValueError(parse_error)
            MedicalEvaluation.model_validate(prediction)
            schema_valid = True
            validated = validate_output(raw, EvaluationRequest.model_validate(payload))
            return {"parsed": validated, "schema_valid": True, "contract_valid": True}
        except ServiceError as exc:
            error = {"type": "contract", "code": exc.code}
        except Exception as exc:
            error = {"type": "schema" if prediction is not None else "parse",
                     "code": type(exc).__name__, "message": str(exc)[:1000]}
        return {"parsed": prediction, "schema_valid": schema_valid,
                "contract_valid": False, "error": error}
    from src.teaching.apply_teaching_guards import apply_teaching_guards
    from src.teaching.evaluate_baseline import evaluate_prediction
    from src.teaching.validate_dataset import contract_errors, prediction_metrics
    prediction, proxy, errors = evaluate_prediction(payload, raw)
    valid = prediction is not None and not contract_errors(prediction)
    guarded, guarded_proxy, guarded_errors = None, {}, ["Raw schema invalid"]
    if valid:
        guarded = apply_teaching_guards(payload, prediction)
        guarded_proxy, guarded_errors = prediction_metrics(payload, guarded)
    return {"parsed": prediction, "schema_valid": valid, "contract_valid": valid,
            "raw_proxy": proxy, "raw_errors": errors, "guarded": guarded,
            "guarded_proxy": guarded_proxy, "guarded_errors": guarded_errors,
            **({"error": {"type": "parse_or_schema", "message": errors}} if not valid else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", choices=["medical_base", "medical_adapter", "teaching_base", "teaching_adapter"])
    args = parser.parse_args()
    config = args.config
    kind, adapter_mode = config.split("_")
    model = base_model = tokenizer = None
    done = threading.Event()
    report = {"config": config, "status": "starting", "pid": os.getpid()}
    destination = RUN / (config + "-process.json")
    baseline = system_snapshot()
    started = time.perf_counter()
    peak_rss = [0]
    samples = rows(DATA / (kind + "-inputs.jsonl"))
    split = read(DATA / "split.json")
    if kind == "medical":
        samples = [r for r in samples if r["split"] == "test" or r["sample_id"] in split["medical_dev_smoke_ids"]]
    samples.sort(key=lambda r: (r["split"] != "development", r["sample_id"]))
    try:
        frozen()
        assert read(RUN / "preflight.json")["expected_roundtrip_valid"]
        check_capacity(kind)
        base, adapter, identity = check(kind)
        import torch
        import psutil
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed

        def sample_memory():
            process = psutil.Process()
            while not done.wait(.5):
                peak_rss[0] = max(peak_rss[0], process.memory_info().rss)

        sampler = threading.Thread(target=sample_memory, daemon=True)
        sampler.start()
        set_seed(42)
        torch.cuda.reset_peak_memory_stats()
        if kind == "medical":
            from src.medical.inference import load_model
            tokenizer, base_model = load_model(base, local_files_only=True)
        else:
            tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True)
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token
            base_model = AutoModelForCausalLM.from_pretrained(
                base, local_files_only=True, device_map={"": 0}, dtype=torch.float16,
                low_cpu_mem_usage=True, attn_implementation="sdpa",
                quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True))
        model = (PeftModel.from_pretrained(base_model, str(adapter), local_files_only=True,
                    is_trainable=False, device_map={"": 0}) if adapter_mode == "adapter" else base_model)
        model.eval()
        model.generation_config.do_sample = False
        model.generation_config.temperature = 0.0 if kind == "teaching" else None
        model.generation_config.top_p = model.generation_config.top_k = None
        max_new = 1200 if kind == "medical" else 1600
        metadata = {"base_model": identity["model_id"], "base_revision": identity["base_revision"],
            "adapter_enabled": adapter_mode == "adapter",
            "adapter_sha256": identity["adapter_sha256"] if adapter_mode == "adapter" else None,
            "tokenizer_config_sha256": identity["base_tokenizer_config_sha256"],
            "chat_template_sha256": fingerprint(tokenizer.chat_template),
            "system_prompt_sha256": fingerprint(messages(kind, samples[0]["payload"])[0]["content"]),
            "generation": {"max_new_tokens": max_new, "input_limit": 4096, "context_limit": 8192,
                "do_sample": False, "seed": 42, "temperature": model.generation_config.temperature,
                "eos_token_id": model.generation_config.eos_token_id,
                "pad_token_id": tokenizer.pad_token_id, "batch_size": 1},
            "quantization": "NF4 double quant float16", "attention": str(base_model.config._attn_implementation),
            "packages": {p: importlib.metadata.version(p) for p in (
                "torch", "transformers", "peft", "accelerate", "bitsandbytes")},
            "dataset_manifest_sha256": file_hash(DATA / "manifest.json"),
            "worker_code_sha256": file_hash(ROOT / "local_model_testing/experiment/worker.py")}
        fp = fingerprint(metadata)
        report.update(status="running", metadata=metadata, fingerprint=fp,
                      load_and_artifact_check_seconds=time.perf_counter() - started,
                      before=baseline)
        write(destination, report)
        errors_in_a_row = 0
        cache_count = 0
        for index, row in enumerate(samples):
            target = RUN / config / (row["sample_id"] + ".json")
            if target.exists():
                if read(target)["fingerprint"] != fp:
                    raise ValueError("CHECKPOINT_CONFIGURATION_MISMATCH")
                cache_count += 1
                continue
            prior = [r for r in ledger.report() if r["config"] == config and r["sample_id"] == row["sample_id"]]
            if prior:
                # A killed attempt is not silently resubmitted on resume.
                write(target, {"sample_id": row["sample_id"], "fingerprint": fp,
                    "attempt_id": prior[0]["id"], "schema_valid": False, "contract_valid": False,
                    "error": {"type": "interrupted", "message": "Reserved attempt had no checkpoint; no automatic retry"}})
                continue
            if shutil.disk_usage(RUN).free < 5 * 1024**3:
                raise RuntimeError("DISK_FREE_BELOW_5_GIB; stopped cleanly")
            category = "development" if row["split"] == "development" else kind + "_final"
            attempt = ledger.reserve(config, row["sample_id"], category, fp)
            item = {"sample_id": row["sample_id"], "fingerprint": fp, "attempt_id": attempt,
                    "payload_sha256": fingerprint(row["payload"]), "split": row["split"],
                    "shard": index // 25, "generation_started": False}
            case_start = time.perf_counter()
            try:
                chat = messages(kind, row["payload"])
                inputs = tokenizer.apply_chat_template(chat, tokenize=True, add_generation_prompt=True,
                                                       return_dict=True, return_tensors="pt")
                count = inputs["input_ids"].shape[-1]
                if count > 4096 or count + max_new > min(8192, model.config.max_position_embeddings):
                    raise ValueError("INPUT_OR_CONTEXT_LIMIT; no truncation")
                item.update(input_tokens=count, actual_prompt_sha256=fingerprint(
                    tokenizer.decode(inputs["input_ids"][0], skip_special_tokens=False)))
                inputs = {k: v.to(model.get_input_embeddings().weight.device) for k, v in inputs.items()}
                kwargs = {"max_new_tokens": max_new, "do_sample": False,
                          "pad_token_id": tokenizer.pad_token_id}
                if kind == "medical":
                    kwargs["eos_token_id"] = model.generation_config.eos_token_id
                else:
                    kwargs["temperature"] = 0.0
                ledger.generation_started(attempt)
                item["generation_started"] = True
                torch.cuda.synchronize()
                tick = time.perf_counter()
                with torch.inference_mode():
                    output = model.generate(**inputs, **kwargs)
                torch.cuda.synchronize()
                item["generation_seconds"] = time.perf_counter() - tick
                tokens = output[0, count:]
                last = int(tokens[-1]) if tokens.numel() else None
                eos = model.generation_config.eos_token_id
                eos_ids = eos if isinstance(eos, list) else [eos]
                raw = tokenizer.decode(tokens, skip_special_tokens=True).strip()
                item.update(generated_tokens=int(tokens.numel()), stopped_at_eos=last in eos_ids,
                            hit_token_cap=int(tokens.numel()) == max_new,
                            truncated=int(tokens.numel()) == max_new and last not in eos_ids)
                write(RUN / config / "raw" / (row["sample_id"] + ".json"),
                      {"text": raw, "attempt_id": attempt, "fingerprint": fp})
                item.update(parse(kind, row["payload"], raw))
                errors_in_a_row = 0
                del output, tokens, inputs
            except Exception as exc:
                item.update(schema_valid=False, contract_valid=False,
                            error={"type": "generation" if item["generation_started"] else "preflight",
                                   "exception": type(exc).__name__, "message": str(exc)[:2000]})
                errors_in_a_row += 1
                if "out of memory" in str(exc).casefold():
                    errors_in_a_row = 3
            item["wall_seconds"] = time.perf_counter() - case_start
            write(target, item)  # Both success and failure are terminal checkpoints.
            ledger.finish(attempt, "completed" if item.get("contract_valid") else "failed",
                          json.dumps(item.get("error")))
            print(config, index + 1, "/", len(samples), row["sample_id"],
                  "valid" if item.get("contract_valid") else "recorded_error", flush=True)
            if errors_in_a_row >= 3:
                raise RuntimeError("THREE_CONSECUTIVE_RUNTIME_ERRORS_OR_OOM; remaining not run")
        report.update(status="finished", cache_hits=cache_count)
    except Exception as exc:
        report.update(status="failed_or_partial", error={"type": type(exc).__name__, "message": str(exc)[:2000]})
        print(config, "stopped:", type(exc).__name__, str(exc)[:200], flush=True)
    finally:
        try:
            import torch
            if torch.cuda.is_initialized():
                report.update(peak_vram_allocated_bytes=torch.cuda.max_memory_allocated(),
                              peak_vram_reserved_bytes=torch.cuda.max_memory_reserved())
        except ImportError:
            pass
        done.set()
        if "sampler" in locals():
            sampler.join(timeout=2)
        report.update(peak_process_rss_bytes=peak_rss[0], total_wall_seconds=time.perf_counter()-started)
        model = base_model = tokenizer = None
        gc.collect()
        if "torch" in locals() and torch.cuda.is_initialized():
            torch.cuda.empty_cache()
        report["cleanup"] = "Python references released; controller must wait for actual container exit"
        write(destination, report)


if __name__ == "__main__":
    main()
