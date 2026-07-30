from pathlib import Path
import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0"    

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "sample_data" / "teaching_train.jsonl"
OUTPUT_DIR = ROOT / "outputs" / "teaching-smoke"
ADAPTER_DIR = OUTPUT_DIR / "adapter"


def main() -> None:
    dataset = load_dataset(
        "json",
        data_files=str(DATA_FILE),
        split="train",
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.pad_token = tokenizer.eos_token

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    lora = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
    )

    config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=1,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to="none",
        fp16=True,
        max_length=512,
        packing=False,
    )

    trainer = SFTTrainer(
        model=MODEL_ID,
        args=config,
        train_dataset=dataset,
        processing_class=tokenizer,
        quantization_config=quantization,
        peft_config=lora,
    )

    trainer.train()
    trainer.save_model(str(ADAPTER_DIR))
    tokenizer.save_pretrained(str(ADAPTER_DIR))

    print(f"Đã lưu adapter tại: {ADAPTER_DIR}")


if __name__ == "__main__":
    main()