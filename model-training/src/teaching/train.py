"""Teaching V1 QLoRA. CUDA only; smoke and full outputs are isolated.

Dependencies: CUDA torch, transformers>=4.57,<5, peft>=0.17,<1,
accelerate>=1.10,<2, bitsandbytes>=0.47,<1. No TRL dependency.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MAX_SEQ_LENGTH = 2048
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "model-training/prepared-data/teaching"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
TRAIN_CONFIG = {
    "num_train_epochs": 3, "per_device_train_batch_size": 1,
    "per_device_eval_batch_size": 1, "gradient_accumulation_steps": 8,
    "learning_rate": 1e-4, "fp16": True, "bf16": False,
    "gradient_checkpointing": True,
    "gradient_checkpointing_kwargs": {"use_reentrant": False},
    "optim": "paged_adamw_8bit", "weight_decay": 0.01,
    "warmup_ratio": 0.1, "seed": 42, "data_seed": 42,
    "eval_strategy": "epoch", "save_strategy": "no",
    "logging_strategy": "steps", "logging_steps": 1,
    "logging_nan_inf_filter": False, "prediction_loss_only": True,
    "report_to": "none", "label_names": ["labels"], "dataloader_num_workers": 0,
    # Keep peak CUDA counters under this script's control.
    "skip_memory_metrics": True,
}


def output_directory(smoke):
    name = "teaching-qwen2.5-smoke" if smoke else "teaching-qwen2.5-v1"
    return ROOT / "model-training/outputs" / name


def load_datasets(smoke=False):
    rows = []
    for split, expected in (("train", 35), ("validation", 10)):
        path = DATA_DIR / f"teaching_{split}_sft.jsonl"
        samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(samples) != expected or len({r["sample_id"] for r in samples}) != expected:
            raise ValueError(f"{split}: expected {expected} unique samples")
        rows.append(samples)
    # Question/case IDs come from the prepared sample IDs; no raw splits loaded.
    import re
    question_sets = []
    for samples in rows:
        qids = set()
        for row in samples:
            match = re.fullmatch(r"TEACH_MED_(\d{4})_\d{2}_V\d{2}", row["sample_id"])
            if not match or match[1] in {"0002", "0009"}:
                raise ValueError("Invalid sample ID or locked Medical question")
            qids.add(match[1])
        question_sets.append(qids)
    if question_sets[0] & question_sets[1]:
        raise ValueError("Train/validation question leakage")
    return (rows[0][:4], rows[1][:2]) if smoke else (rows[0], rows[1])


def encode_sample(row, tokenizer):
    messages = row["messages"]
    if [m["role"] for m in messages] != ["system", "user", "assistant"]:
        raise ValueError(f"{row['sample_id']}: invalid chat roles")
    if any(not isinstance(m["content"], str) or not m["content"].strip() for m in messages):
        raise ValueError("Empty/non-string message")
    prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
    tokens = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    boundary = len(prompt)
    if not boundary or tokens[:boundary] != prompt or boundary >= len(tokens):
        raise ValueError("Assistant boundary does not match inference prompt")
    if len(tokens) > MAX_SEQ_LENGTH:
        raise ValueError(f"{row['sample_id']}: {len(tokens)} > {MAX_SEQ_LENGTH}; no truncation")
    if tokenizer.decode(tokens[boundary:], skip_special_tokens=True).strip() != messages[-1]["content"].strip():
        raise ValueError("Assistant tokens do not match unchanged gold")
    return {"input_ids": tokens, "attention_mask": [1] * len(tokens),
            "labels": [-100] * boundary + tokens[boundary:]}


class AssistantOnlyCollator:
    def __init__(self, pad_token_id):
        self.pad_token_id = pad_token_id

    def __call__(self, features):
        import torch
        length = max(len(f["input_ids"]) for f in features)
        batch = {}
        for key, pad in (("input_ids", self.pad_token_id), ("attention_mask", 0), ("labels", -100)):
            batch[key] = torch.tensor(
                [f[key] + [pad] * (length - len(f[key])) for f in features], dtype=torch.long,
            )
        return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="4 train/2 validation, one optimizer step")
    cli = parser.parse_args()
    output_dir = output_directory(cli.smoke_test)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing run: {output_dir}")
    train_rows, validation_rows = load_datasets(cli.smoke_test)
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required; training on CPU is disabled")
    if int(os.environ.get("WORLD_SIZE", "1")) != 1 or torch.cuda.device_count() != 1:
        raise RuntimeError("Use one visible GPU and python, not torchrun")
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                              Trainer, TrainerCallback, TrainingArguments, set_seed)

    class FiniteTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            result = super().compute_loss(model, inputs, return_outputs=return_outputs,
                                          num_items_in_batch=num_items_in_batch)
            loss = result[0] if return_outputs else result
            if not torch.isfinite(loss.detach()).all().item():
                raise FloatingPointError("Non-finite train/validation loss")
            return result

    class Monitor(TrainerCallback):
        trainer = None
        successful_steps = 0

        def on_step_end(self, args, state, control, **kwargs):
            if not self.trainer.accelerator.optimizer_step_was_skipped:
                self.successful_steps += 1

        def on_log(self, args, state, control, logs=None, **kwargs):
            for key in ("loss", "eval_loss", "grad_norm"):
                if key in (logs or {}) and not math.isfinite(float(logs[key])):
                    raise FloatingPointError(f"Non-finite {key}")

    set_seed(42)
    torch.cuda.reset_peak_memory_stats()
    initial_vram = {"allocated_bytes": torch.cuda.memory_allocated(),
                    "reserved_bytes": torch.cuda.memory_reserved()}
    print(f"GPU: {torch.cuda.get_device_name(0)} | Initial VRAM: {initial_vram}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    train_data = [encode_sample(r, tokenizer) for r in train_rows]
    validation_data = [encode_sample(r, tokenizer) for r in validation_rows]
    print(f"Assistant-only masking PASS | train={len(train_data)} validation={len(validation_data)}")
    quant_config = {"load_in_4bit": True, "bnb_4bit_quant_type": "nf4",
                    "bnb_4bit_compute_dtype": "float16", "bnb_4bit_use_double_quant": True}
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype=torch.float16, device_map={"": 0}, low_cpu_mem_usage=True,
        attn_implementation="sdpa", quantization_config=BitsAndBytesConfig(
            **{**quant_config, "bnb_4bit_compute_dtype": torch.float16}),
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                           gradient_checkpointing_kwargs={"use_reentrant": False})
    lora_config = {"r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
                   "task_type": "CAUSAL_LM", "target_modules": TARGET_MODULES, "bias": "none"}
    model = get_peft_model(model, LoraConfig(**lora_config))
    trainable_params, total_params = model.get_nb_trainable_parameters()
    model.print_trainable_parameters()
    trainable = {n: p for n, p in model.named_parameters() if p.requires_grad}
    if not trainable or any("lora_" not in n for n in trainable):
        raise RuntimeError("Only LoRA parameters may be trainable")
    initial_weights = {n: p.detach().cpu().clone() for n, p in trainable.items()} if cli.smoke_test else {}
    run_config = dict(TRAIN_CONFIG)
    if cli.smoke_test:
        # One-step warmup would set the only optimizer update's LR to zero.
        # Smoke verifies a real weight update; full V1 retains warmup_ratio=0.1.
        run_config["warmup_ratio"] = 0.0
    args = TrainingArguments(output_dir=str(output_dir), max_steps=1 if cli.smoke_test else -1,
                             **run_config)
    monitor = Monitor()
    trainer = FiniteTrainer(model=model, args=args, train_dataset=train_data,
                            eval_dataset=validation_data, processing_class=tokenizer,
                            data_collator=AssistantOnlyCollator(tokenizer.pad_token_id), callbacks=[monitor])
    monitor.trainer = trainer
    result = trainer.train()
    evaluation = trainer.evaluate()
    if not math.isfinite(result.training_loss) or not math.isfinite(evaluation["eval_loss"]):
        raise FloatingPointError("Non-finite final losses")
    if cli.smoke_test:
        if trainer.state.global_step != 1 or monitor.successful_steps != 1:
            raise RuntimeError("Smoke failed: optimizer update skipped (possible FP16 overflow)")
        if not any(not torch.equal(initial_weights[n], p.detach().cpu()) for n, p in trainable.items()):
            raise RuntimeError("Smoke failed: adapter weights unchanged")
    if any(not torch.isfinite(p.detach()).all().item() for p in trainable.values()):
        raise FloatingPointError("Non-finite adapter weights")
    adapter_dir = output_dir / "adapter"
    model.save_pretrained(adapter_dir, safe_serialization=True)
    tokenizer.save_pretrained(adapter_dir)
    for filename in ("adapter_config.json", "adapter_model.safetensors"):
        path = adapter_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Adapter file missing/empty: {filename}")
    summary = {
        "model_id": MODEL_ID, "smoke_test": cli.smoke_test, "max_seq_length": MAX_SEQ_LENGTH,
        "quantization": quant_config, "lora": lora_config, "training_arguments": args.to_dict(),
        "model_loading": {"dtype": "float16", "device_map": {"": 0}, "attn_implementation": "sdpa",
                          "low_cpu_mem_usage": True, "use_cache": False},
        "train_samples": len(train_data), "validation_samples": len(validation_data),
        "sample_ids": {"train": [r["sample_id"] for r in train_rows],
                       "validation": [r["sample_id"] for r in validation_rows]},
        "dataset_sha256": {s: hashlib.sha256((DATA_DIR / f"teaching_{s}_sft.jsonl").read_bytes()).hexdigest()
                           for s in ("train", "validation")},
        "gpu": torch.cuda.get_device_name(0), "torch_version": torch.__version__,
        "trainable_params": trainable_params, "total_params": total_params,
        "trainable_percent": 100 * trainable_params / total_params,
        "vram": {"initial": initial_vram, "max_allocated_bytes": torch.cuda.max_memory_allocated(),
                 "max_reserved_bytes": torch.cuda.max_memory_reserved()},
        "successful_optimizer_steps": monitor.successful_steps,
        "train_runtime": result.metrics["train_runtime"], "train_loss": result.training_loss,
        "eval_loss": evaluation["eval_loss"], "train_metrics": result.metrics, "eval_metrics": evaluation,
        "adapter_dir": str(adapter_dir), "supervision": "assistant-only; prompt/padding masked; no truncation",
    }
    trainer.save_state()
    (output_dir / "training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("SMOKE TEST PASS" if cli.smoke_test else "TEACHING V1 TRAINING COMPLETED")


if __name__ == "__main__":
    main()
