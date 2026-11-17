"""Teaching V1 serving only; original prompt, decoding and deterministic guards."""

import gc
import hashlib
import importlib.metadata
import json
import os
import time

from src.medical.validation import MedicalEvaluation
from src.teaching.apply_teaching_guards import apply_teaching_guards
from src.teaching.evaluate_adapter import MAX_NEW_TOKENS
from src.teaching.evaluate_baseline import MODEL_ID
from src.teaching.prepare_dataset import SYSTEM_PROMPT
from src.teaching.validate_dataset import contract_errors, input_errors, prediction_metrics, rules

from .runner import Generation, check_artifacts
from .validation import ServiceError, strict_json


def validate_teaching_input(raw: bytes) -> dict:
    try:
        payload = strict_json(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != rules.REQUIRED_INPUT:
            raise ValueError("Teaching fields")
        if input_errors(payload):
            raise ValueError("Teaching input")
        MedicalEvaluation.model_validate(payload["medical_evaluation"])
        return payload
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise ServiceError("TEACHING_INPUT_INVALID", 422) from None


def validate_teaching_output(raw: str, payload: dict) -> dict:
    try:
        prediction = strict_json(raw)
        if contract_errors(prediction):
            raise ServiceError("TEACHING_OUTPUT_INVALID_SCHEMA", 502)
        guarded = apply_teaching_guards(payload, prediction)
        metrics, errors = prediction_metrics(payload, guarded)
        if errors or not all(metrics.values()):
            raise ServiceError("TEACHING_ALIGNMENT_INVALID", 502)
        return guarded
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ServiceError("TEACHING_OUTPUT_INVALID_JSON", 502) from None


class TeachingRunner:
    def __init__(self, settings):
        self.settings = settings
        self.metadata = {}
        self.model = self.base_model = self.tokenizer = None

    def _check(self):
        return check_artifacts(
            self.settings,
            model_id=MODEL_ID,
            model_type="qwen2",
            adapter_id="teaching-v1",
            system_prompt=SYSTEM_PROMPT,
            max_new_tokens=MAX_NEW_TOKENS,
            prompt_id="teaching-v1-original",
        )

    def load(self):
        self.metadata = self._check()
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed

        if not torch.cuda.is_available():
            raise ServiceError("CUDA_REQUIRED", 503)
        set_seed(42)
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.settings.base_path, local_files_only=True
        )
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.base_model = AutoModelForCausalLM.from_pretrained(
            self.settings.base_path,
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
            str(self.settings.adapter_path),
            local_files_only=True,
            is_trainable=False,
            device_map={"": 0},
        )
        self.model.eval()
        self.model.generation_config.do_sample = False
        self.model.generation_config.temperature = 0.0
        self.model.generation_config.top_p = self.model.generation_config.top_k = None
        self._check()
        template = self.tokenizer.chat_template
        if not template:
            raise ServiceError("TOKENIZER_CHAT_TEMPLATE_MISSING", 503)
        self.metadata.update(
            chat_template_sha256=hashlib.sha256(
                (
                    template if isinstance(template, str) else json.dumps(template, sort_keys=True)
                ).encode()
            ).hexdigest(),
            packages={
                p: importlib.metadata.version(p)
                for p in ("torch", "transformers", "peft", "accelerate", "bitsandbytes")
            },
            limits={
                "max_input_tokens": self.settings.max_input_tokens,
                "max_context_tokens": self.settings.max_context_tokens,
            },
        )
        self.metadata["generation"].update(
            temperature=0,
            seed=42,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.model.generation_config.eos_token_id,
        )

    def generate(self, payload):
        import torch

        if input_errors(payload):
            raise ServiceError("TEACHING_INPUT_INVALID", 422)
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
        if count > self.settings.max_input_tokens:
            raise ServiceError("INPUT_TOKEN_LIMIT", 413)
        if count + MAX_NEW_TOKENS > min(
            self.settings.max_context_tokens, self.model.config.max_position_embeddings
        ):
            raise ServiceError("CONTEXT_LIMIT", 413)
        inputs = {
            k: v.to(self.model.get_input_embeddings().weight.device) for k, v in inputs.items()
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
        return Generation(raw, time.perf_counter() - start, count, tokens.numel())

    def close(self):
        self.model = self.base_model = self.tokenizer = None
        gc.collect()
