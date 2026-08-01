import os
from pathlib import Path

# Chỉ cho chương trình nhìn thấy GPU đầu tiên của Kaggle.
# Phải đặt trước khi import torch.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["ACCELERATE_MIXED_PRECISION"] = "no"

import torch
from datasets import load_dataset
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
)
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
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

    tokenizer.padding_side = "right"

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quantization_config,
        dtype=torch.float16,
        device_map={"": 0},
    )

    model.config.use_cache = False

    # Chuẩn bị model lượng tử hóa cho QLoRA.
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
        bias="none",
    )

    # Gắn adapter trước khi đưa model vào Trainer.
    model = get_peft_model(model, lora_config)

    # Đảm bảo tham số LoRA không bị giữ ở BFloat16 trên Tesla T4.
    for parameter in model.parameters():
        if parameter.requires_grad:
            parameter.data = parameter.data.to(torch.float32)

    model.print_trainable_parameters()

    training_config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to="none",
        fp16=True,
        bf16=False,
        max_length=512,
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()

    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    trainer.model.save_pretrained(ADAPTER_DIR)
    tokenizer.save_pretrained(ADAPTER_DIR)

    print(f"Đã lưu LoRA adapter tại: {ADAPTER_DIR}")


if __name__ == "__main__":
    main()