import gc
import hashlib
import importlib.metadata
import json
from dataclasses import dataclass
from typing import Protocol

from src.medical.inference import (
    MAX_NEW_TOKENS,
    MODEL_ID,
    SYSTEM_PROMPT,
    build_user_content,
    generate_text,
    load_model,
)

from .config import Settings
from .validation import ServiceError, strict_json


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_artifacts(settings):
    base, adapter = settings.base_path, settings.adapter_path
    for directory, code in (
        (base, "BASE_DIRECTORY_MISSING"),
        (adapter, "ADAPTER_DIRECTORY_MISSING"),
    ):
        if not directory.is_dir():
            raise ServiceError(code, 503)
    for path, code in (
        (base / "config.json", "BASE_CONFIG_MISSING"),
        (base / "tokenizer_config.json", "BASE_TOKENIZER_CONFIG_MISSING"),
        (adapter / "adapter_config.json", "ADAPTER_CONFIG_MISSING"),
        (adapter / "adapter_model.safetensors", "ADAPTER_WEIGHTS_MISSING"),
    ):
        if not path.is_file() or path.stat().st_size == 0:
            raise ServiceError(code, 503)
    if not list(base.glob("*.safetensors")) and not list(base.glob("pytorch_model*.bin")):
        raise ServiceError("BASE_WEIGHTS_MISSING", 503)
    if sha256(adapter / "adapter_model.safetensors") != settings.adapter_sha256:
        raise ServiceError("ADAPTER_HASH_MISMATCH", 503)
    if sha256(base / "config.json") != settings.base_config_sha256:
        raise ServiceError("BASE_CONFIG_HASH_MISMATCH", 503)
    if sha256(adapter / "adapter_config.json") != settings.adapter_config_sha256:
        raise ServiceError("ADAPTER_CONFIG_HASH_MISMATCH", 503)
    try:
        config = strict_json((adapter / "adapter_config.json").read_text(encoding="utf-8"))
        base_config = strict_json((base / "config.json").read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ServiceError("ARTIFACT_CONFIG_INVALID", 503) from None
    if (
        config.get("base_model_name_or_path") != MODEL_ID
        or config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
    ):
        raise ServiceError("ADAPTER_IDENTITY_MISMATCH", 503)
    if base_config.get("model_type") != "qwen3":
        raise ServiceError("BASE_IDENTITY_MISMATCH", 503)
    return {
        "model_id": MODEL_ID,
        "base_config_sha256": settings.base_config_sha256,
        "adapter_id": "medical-qwen3-pilot",
        "adapter_sha256": settings.adapter_sha256,
        "adapter_config_sha256": settings.adapter_config_sha256,
        "service_version": "0.1.0",
        "prompt_id": "medical-pilot-original",
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "quantization": {
            "load_in_4bit": True,
            "quant_type": "nf4",
            "double_quant": True,
            "compute_dtype": "float16",
        },
        "generation": {
            "max_new_tokens": MAX_NEW_TOKENS,
            "do_sample": False,
            "temperature": None,
            "top_p": None,
            "top_k": None,
        },
    }


@dataclass
class Generation:
    text: str
    inference_seconds: float
    input_tokens: int
    generated_tokens: int


class Runner(Protocol):
    metadata: dict

    def load(self) -> None: ...
    def generate(self, payload: dict) -> Generation: ...
    def close(self) -> None: ...


class PilotRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.metadata = {}
        self.model = self.base_model = self.tokenizer = None

    def load(self):
        # Verify local paths/hash before importing GPU libraries. Never download weights.
        self.metadata = check_artifacts(self.settings)
        import os

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from peft import PeftModel

        if not torch.cuda.is_available():
            raise ServiceError("CUDA_REQUIRED", 503)
        self.tokenizer, self.base_model = load_model(self.settings.base_path, local_files_only=True)
        self.model = PeftModel.from_pretrained(
            self.base_model,
            str(self.settings.adapter_path),
            is_trainable=False,
            device_map={"": 0},
            local_files_only=True,
        )
        self.model.eval()
        # Readiness is never granted after artifacts changed during startup.
        check_artifacts(self.settings)
        # Record the actual chat template and environment, not an assumed tokenizer revision.
        template = self.tokenizer.chat_template
        if not template:
            raise ServiceError("TOKENIZER_CHAT_TEMPLATE_MISSING", 503)
        template_text = (
            template if isinstance(template, str) else json.dumps(template, sort_keys=True)
        )
        self.metadata.update(
            {
                "chat_template_sha256": hashlib.sha256(template_text.encode("utf-8")).hexdigest(),
                "packages": {
                    name: importlib.metadata.version(name)
                    for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes")
                },
                "limits": {
                    "max_input_tokens": self.settings.max_input_tokens,
                    "max_context_tokens": self.settings.max_context_tokens,
                },
            }
        )
        self.metadata["generation"].update(
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.model.generation_config.eos_token_id,
        )

    def generate(self, payload):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_content(payload)},
        ]
        try:
            raw, elapsed, inputs, generated = generate_text(
                messages,
                self.tokenizer,
                self.model,
                max_input_tokens=self.settings.max_input_tokens,
                max_context_tokens=self.settings.max_context_tokens,
            )
        except ValueError as exc:
            if str(exc) in {"INPUT_TOKEN_LIMIT", "CONTEXT_LIMIT"}:
                raise ServiceError(str(exc), 413) from None
            raise
        return Generation(raw, elapsed, inputs, generated)

    def close(self):
        self.model = self.base_model = self.tokenizer = None
        gc.collect()
