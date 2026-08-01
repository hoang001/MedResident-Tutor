import os
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["ACCELERATE_MIXED_PRECISION"] = "no"

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "sample_data" / "teaching_train.jsonl"
OUTPUT_DIR = ROOT / "outputs" / "teaching-smoke"
ADAPTER_DIR = OUTPUT_DIR / "adapter"


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Không phát hiện GPU CUDA.")

    print("GPU:", torch.cuda.get_device_name(0))

    dataset = load_dataset(
        "json",
        data_files=str(DATA_FILE),
        split="train",
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float32,
    ).to("cuda:0")

    model.config.use_cache = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
        bias="none",
    )

    training_config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=1,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to="none",
        fp16=False,
        bf16=False,
        max_length=512,
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_config,
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=lora_config,
    )

    print("Mixed precision:", trainer.accelerator.mixed_precision)

    trainer.train()

    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(ADAPTER_DIR)
    tokenizer.save_pretrained(ADAPTER_DIR)

    print(f"Đã lưu LoRA adapter tại: {ADAPTER_DIR}")


if __name__ == "__main__":
    main()