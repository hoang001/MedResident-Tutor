"""Small local batch wrapper: original V1 prompt, inference settings and guards."""

import gc
import hashlib
import importlib.metadata
import json
import sys
import time

from .common import ROOT

sys.path.insert(0, str(ROOT / "model-training"))
from src.teaching.prepare_dataset import SYSTEM_PROMPT
from src.teaching.apply_teaching_guards import apply_teaching_guards
from src.teaching.evaluate_adapter import MAX_NEW_TOKENS
from src.teaching.evaluate_baseline import evaluate_prediction
from src.teaching.validate_dataset import (
    contract_errors,
    input_errors,
    prediction_metrics,
)


class TeachingRunner:
    def __init__(self, base, adapter, metadata):
        self.base, self.adapter, self.metadata = base, adapter, dict(metadata)
        self.tokenizer = self.base_model = self.model = None

    def load(self):
        import torch
        from peft import PeftModel
        from transformers import (
            AutoTokenizer,
            AutoModelForCausalLM,
            BitsAndBytesConfig,
            set_seed,
        )

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA_REQUIRED; no CPU fallback")
        set_seed(42)
        self.tokenizer = AutoTokenizer.from_pretrained(self.base, local_files_only=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.base_model = AutoModelForCausalLM.from_pretrained(
            self.base,
            local_files_only=True,
            device_map={"": 0},
            dtype=torch.float16,
            low_cpu_mem_usage=True,
            attn_implementation="sdpa",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            ),
        )
        self.model = PeftModel.from_pretrained(
            self.base_model,
            str(self.adapter),
            local_files_only=True,
            is_trainable=False,
            device_map={"": 0},
        )
        self.model.eval()
        self.model.generation_config.do_sample = False
        self.model.generation_config.temperature = 0.0
        self.model.generation_config.top_p = self.model.generation_config.top_k = None
        template = self.tokenizer.chat_template
        if not template:
            raise ValueError("TOKENIZER_CHAT_TEMPLATE_MISSING")
        self.metadata.update(
            {
                "system_prompt_sha256": hashlib.sha256(
                    SYSTEM_PROMPT.encode()
                ).hexdigest(),
                "chat_template_sha256": hashlib.sha256(
                    (
                        template
                        if isinstance(template, str)
                        else json.dumps(template, sort_keys=True)
                    ).encode()
                ).hexdigest(),
                "packages": {
                    p: importlib.metadata.version(p)
                    for p in (
                        "torch",
                        "transformers",
                        "peft",
                        "accelerate",
                        "bitsandbytes",
                    )
                },
                "generation": {
                    "max_new_tokens": MAX_NEW_TOKENS,
                    "do_sample": False,
                    "temperature": 0,
                    "seed": 42,
                },
                "quantization": "NF4 double quant float16; batch 1; CUDA 0",
                "limits": {"input_tokens": 4096, "context_tokens": 8192},
            }
        )

    def generate(self, payload):
        import torch

        errors = input_errors(payload)
        if errors:
            raise ValueError("TEACHING_INPUT_INVALID: " + "; ".join(errors))
        content = {
            k: payload[k]
            for k in (
                "question",
                "student_answer",
                "medical_evaluation",
                "learner_context",
                "metadata",
            )
        }
        inputs = self.tokenizer.apply_chat_template(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(content, ensure_ascii=False)},
            ],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        count = inputs["input_ids"].shape[-1]
        if count > 4096 or count + MAX_NEW_TOKENS > min(
            8192, self.model.config.max_position_embeddings
        ):
            raise ValueError("CONTEXT_LIMIT; no truncation")
        inputs = {
            k: v.to(self.model.get_input_embeddings().weight.device)
            for k, v in inputs.items()
        }
        torch.cuda.synchronize()
        start = time.perf_counter()
        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                temperature=0.0,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        torch.cuda.synchronize()
        tokens = output[0, count:]
        raw = self.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        prediction, raw_metrics, raw_errors = evaluate_prediction(payload, raw)
        guarded = None
        guard_metrics, guard_errors = {}, ["Raw output not valid Teaching schema"]
        if prediction is not None and not contract_errors(prediction):
            guarded = apply_teaching_guards(payload, prediction)
            guard_metrics, guard_errors = prediction_metrics(payload, guarded)
        return {
            "raw_text": raw,
            "raw_prediction": prediction,
            "raw_metrics": raw_metrics,
            "raw_errors": raw_errors,
            "guarded_prediction": guarded,
            "guard_metrics": guard_metrics,
            "guard_errors": guard_errors,
            "inference_seconds": time.perf_counter() - start,
            "input_tokens": count,
            "generated_tokens": tokens.numel(),
            "manual_feedback_review_required": True,
        }

    def close(self):
        self.model = self.base_model = self.tokenizer = None
        gc.collect()
