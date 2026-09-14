"""Medical QLoRA pilot. Run directly with --smoke-test before full training.

Dependencies: CUDA PyTorch, transformers>=4.57,<5, peft>=0.17,<1,
accelerate>=1.10,<2, bitsandbytes>=0.47,<1. No TRL dependency.
"""

import argparse
import json
import math
import os
from pathlib import Path


MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MAX_SEQ_LENGTH = 4096
SMOKE_STEPS = 3


def find_repo_root() -> Path:
    # Same convention as evaluate_baseline.py; avoid importing its mkdir side effect.
    current = Path(__file__).resolve()
    for directory in [current.parent, *current.parents]:
        if (
            (directory / ".git").exists()
            and (directory / "model-training").exists()
        ):
            return directory
    raise RuntimeError("Không tìm thấy repository root. Hãy chạy từ một git clone.")


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}: JSON lỗi tại dòng {line_number}") from exc
    if not rows:
        raise ValueError(f"Dataset rỗng: {path}")
    return rows


def encode_sample(row, tokenizer):
    """Mask the entire inference prompt, supervise the answer and turn terminator."""
    sample_id = row["sample_id"]
    messages = row["messages"]
    if [message["role"] for message in messages] != ["system", "user", "assistant"]:
        raise ValueError(f"{sample_id}: cần đúng system/user/assistant.")
    if any(not isinstance(m["content"], str) or not m["content"].strip() for m in messages):
        raise ValueError(f"{sample_id}: content phải là chuỗi không rỗng.")

    # Match the existing evaluator's generation prompt exactly.
    prompt_ids = tokenizer.apply_chat_template(
        messages[:-1], tokenize=True, add_generation_prompt=True,
    )
    input_ids = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False,
    )
    boundary = len(prompt_ids)
    if not boundary or input_ids[:boundary] != prompt_ids:
        raise ValueError(f"{sample_id}: chat template không có token prefix khớp prompt.")
    if len(input_ids) > MAX_SEQ_LENGTH:
        raise ValueError(
            f"{sample_id}: {len(input_ids)} tokens > {MAX_SEQ_LENGTH}; không tự truncate."
        )
    if boundary >= len(input_ids):
        raise ValueError(f"{sample_id}: không có assistant tokens để tính loss.")
    response = tokenizer.decode(input_ids[boundary:], skip_special_tokens=True)
    if response.strip() != messages[-1]["content"].strip():
        raise ValueError(f"{sample_id}: supervised tokens không khớp assistant response.")
    labels = [-100] * boundary + input_ids[boundary:]
    return {"input_ids": input_ids, "attention_mask": [1] * len(input_ids), "labels": labels}


def make_smoke_context(feature):
    """In-memory stress input: repeat masked prompt tokens to reach 4096 active tokens.

    The assistant target is unchanged. These synthetic contexts are smoke-only,
    never written to the prepared dataset and never used in the full run.
    """
    missing = MAX_SEQ_LENGTH - len(feature["input_ids"])
    boundary = next(i for i, label in enumerate(feature["labels"]) if label != -100)
    prompt = feature["input_ids"][:boundary]
    prefix = (prompt * ((missing + boundary - 1) // boundary))[:missing]
    return {
        "input_ids": prefix + feature["input_ids"],
        "attention_mask": [1] * MAX_SEQ_LENGTH,
        "labels": [-100] * missing + feature["labels"],
    }


class AssistantOnlyCollator:
    def __init__(self, pad_token_id):
        self.pad_token_id = pad_token_id

    def __call__(self, features):
        import torch

        length = max(len(item["input_ids"]) for item in features)
        batch = {key: [] for key in ("input_ids", "attention_mask", "labels")}
        for item in features:
            padding = length - len(item["input_ids"])
            for key, pad in (("input_ids", self.pad_token_id), ("attention_mask", 0),
                             ("labels", -100)):
                batch[key].append(item[key] + [pad] * padding)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="3 optimizer steps at 4096 tokens")
    parser.add_argument("--learning-rate", type=float, default=2e-4, help="Learning rate (default: 2e-4)")
    parser.add_argument("--epochs", type=float, default=3, help="Training epochs (default: 3)")
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("model-training/outputs/medical-qwen3-pilot"),
        help="Output directory; relative paths resolve from repository root",
    )
    cli = parser.parse_args()
    if not math.isfinite(cli.learning_rate) or cli.learning_rate <= 0:
        parser.error("--learning-rate must be finite and positive")
    if not math.isfinite(cli.epochs) or cli.epochs <= 0:
        parser.error("--epochs must be finite and positive")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("Cần GPU CUDA để chạy QLoRA; không chạy training trên CPU.")
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise RuntimeError("Pilot này dùng một GPU. Chạy bằng python, không dùng torchrun.")

    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainerCallback,
        TrainingArguments,
        set_seed,
    )

    class FiniteLossTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            result = super().compute_loss(
                model, inputs, return_outputs=return_outputs,
                num_items_in_batch=num_items_in_batch,
            )
            loss = result[0] if return_outputs else result
            if not torch.isfinite(loss.detach()).all().item():
                raise FloatingPointError("Training/validation loss không finite.")
            return result

    class StepMonitor(TrainerCallback):
        def __init__(self):
            self.trainer = None
            self.successful_steps = 0

        def on_step_end(self, args, state, control, **kwargs):
            if not self.trainer.accelerator.optimizer_step_was_skipped:
                self.successful_steps += 1

        def on_log(self, args, state, control, logs=None, **kwargs):
            for key in ("loss", "eval_loss", "grad_norm"):
                if key in (logs or {}) and not math.isfinite(float(logs[key])):
                    raise FloatingPointError(f"{key} không finite: {logs[key]}")

    root = find_repo_root()
    data_dir = root / "model-training" / "prepared-data" / "medical"
    output_dir = cli.output_dir if cli.output_dir.is_absolute() else root / cli.output_dir
    if cli.smoke_test:
        output_dir = output_dir / "smoke-test"
    adapter_dir = output_dir / "adapter"
    if adapter_dir.exists() and any(adapter_dir.iterdir()):
        raise FileExistsError(f"Adapter đã tồn tại; chuyển nó sang nơi khác trước: {adapter_dir}")

    # Explicit allowlist: never discover or load other splits.
    train_rows = read_jsonl(data_dir / "medical_train_sft.jsonl")
    validation_rows = read_jsonl(data_dir / "medical_validation_sft.jsonl")
    if (len(train_rows), len(validation_rows)) != (36, 8):
        raise ValueError("Pilot đã chốt cần 36 train / 8 validation samples.")
    if {r["question_id"] for r in train_rows} & {r["question_id"] for r in validation_rows}:
        raise ValueError("Question leakage giữa train và validation.")
    print(f"Train samples: {len(train_rows)} | Validation samples: {len(validation_rows)}")
    print(f"Model: {MODEL_ID} | Max sequence length: {MAX_SEQ_LENGTH}")
    print(f"GPU: {torch.cuda.get_device_name(0)} | Smoke test: {cli.smoke_test}")
    set_seed(42)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    train_data = [encode_sample(row, tokenizer) for row in train_rows]
    validation_data = [encode_sample(row, tokenizer) for row in validation_rows]
    print("Assistant-only masking: PASS (all 44 samples; prompt/header labels = -100)")
    if cli.smoke_test:
        train_data = [make_smoke_context(item) for item in train_data]
        print("Smoke stress: 4096 active tokens/input; synthetic masked prefix, unchanged target.")

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        ),
        dtype=torch.float16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    model = get_peft_model(model, LoraConfig(
        task_type="CAUSAL_LM", target_modules="all-linear", bias="none",
        r=16, lora_alpha=32, lora_dropout=0.05,
    ))
    model.print_trainable_parameters()
    trainable = {name: param for name, param in model.named_parameters() if param.requires_grad}
    if not trainable or any("lora_" not in name for name in trainable):
        raise RuntimeError("QLoRA attach lỗi: chỉ LoRA parameters được train.")
    initial = {name: param.detach().cpu().clone() for name, param in trainable.items()} \
        if cli.smoke_test else {}

    arguments = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=cli.epochs,
        max_steps=SMOKE_STEPS if cli.smoke_test else -1,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        fp16=True,
        bf16=False,
        learning_rate=cli.learning_rate,
        optim="paged_adamw_8bit",
        eval_strategy="epoch",
        save_strategy="no",
        logging_strategy="steps",
        logging_steps=1,
        logging_nan_inf_filter=False,
        prediction_loss_only=True,
        report_to="none",
        label_names=["labels"],
        seed=42,
        data_seed=42,
        dataloader_num_workers=0,
    )
    monitor = StepMonitor()
    trainer = FiniteLossTrainer(
        model=model, args=arguments,
        train_dataset=train_data, eval_dataset=validation_data,
        data_collator=AssistantOnlyCollator(tokenizer.pad_token_id),
        processing_class=tokenizer, callbacks=[monitor],
    )
    monitor.trainer = trainer
    # Trainer must not activate DataParallel when Kaggle exposes two GPUs.
    if trainer.args.n_gpu != 1:
        raise RuntimeError("Chỉ bật một GPU: đặt CUDA_VISIBLE_DEVICES=0 trước khi chạy.")
    torch.cuda.reset_peak_memory_stats()
    result = trainer.train()
    validation_metrics = trainer.evaluate()
    if not math.isfinite(result.training_loss) or not math.isfinite(validation_metrics["eval_loss"]):
        raise FloatingPointError("Final loss không finite.")
    if cli.smoke_test:
        if trainer.state.global_step != SMOKE_STEPS or monitor.successful_steps != SMOKE_STEPS:
            raise RuntimeError("Smoke FAIL: chưa đủ 3 optimizer updates (có thể FP16 overflow).")
        if not any(not torch.equal(initial[n], p.detach().cpu()) for n, p in trainable.items()):
            raise RuntimeError("Smoke FAIL: LoRA weights không thay đổi.")
    if any(not torch.isfinite(param.detach()).all().item() for param in trainable.values()):
        raise FloatingPointError("Adapter weights không finite.")

    # Save only the PEFT adapter, never merge it with the base model.
    model.save_pretrained(adapter_dir, safe_serialization=True)
    tokenizer.save_pretrained(adapter_dir)
    for filename in ("adapter_config.json", "adapter_model.safetensors"):
        if not (adapter_dir / filename).is_file() or (adapter_dir / filename).stat().st_size == 0:
            raise RuntimeError(f"Không lưu được {filename}")
    metrics = {
        "model_id": MODEL_ID, "smoke_test": cli.smoke_test,
        "train_samples": len(train_rows), "validation_samples": len(validation_rows),
        "max_seq_length": MAX_SEQ_LENGTH,
        "trainable_parameters": sum(p.numel() for p in trainable.values()),
        "successful_optimizer_steps": monitor.successful_steps,
        "peak_vram_gb": torch.cuda.max_memory_allocated() / 1024**3,
        "adapter_dir": str(adapter_dir),
        **result.metrics, **validation_metrics,
    }
    trainer.save_state()
    trainer.save_metrics("run", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"Adapter saved: {adapter_dir}")
    print("SMOKE TEST PASS" if cli.smoke_test else "MEDICAL TRAINING COMPLETED")


if __name__ == "__main__":
    main()
