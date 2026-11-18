"""Authoring on the already-loaded Qwen base, inside the shared GPU lock."""

import json
import math
import time

from .authoring_contract import SYSTEM, VERSION, Proposal, Scope
from .errors import DiagnosticServiceError
from .runner import Generation
from .validation import Evidence, ServiceError, strict_json


def validate_request(raw):
    try:
        payload = strict_json(raw.decode("utf-8"))
        if set(payload) != {"version", "system", "scope", "evidence"}:
            raise ValueError()
        if payload["version"] != VERSION or payload["system"] != SYSTEM:
            raise ValueError()
        Scope.model_validate(payload["scope"])
        evidence = [Evidence.model_validate(e) for e in payload["evidence"]]
        if not 1 <= len(evidence) <= 3:
            raise ValueError()
        if len({e.source_unit_id for e in evidence}) != len(evidence):
            raise ValueError()
        if sum(len(e.content) for e in evidence) > 6000:
            raise ValueError()
        if any(e.page_end < e.page_start or not e.content.strip() for e in evidence):
            raise ValueError()
        return payload
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise ServiceError("AUTHORING_INPUT_INVALID", 422) from None


def validate_output(raw, payload):
    try:
        proposal = Proposal.model_validate(strict_json(raw))
        known = {e["source_unit_id"] for e in payload["evidence"]}
        if any(not set(c.source_unit_ids) <= known for c in proposal.criteria):
            raise ValueError()
        if not math.isclose(
            sum(c.max_score for c in proposal.criteria),
            payload["scope"]["max_score"],
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise ValueError()
        return proposal.model_dump()
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise DiagnosticServiceError(
            "AUTHORING_OUTPUT_INVALID",
            502,
            phase="authoring_validation",
            error_type=type(exc).__name__,
        ) from None


class BaseAuthoringRunner:
    def __init__(self, medical):
        self.medical = medical
        self.metadata = {}

    def load(self):
        self.metadata = {
            "model_id": self.medical.metadata.get("model_id"),
            "base_config_sha256": self.medical.metadata.get("base_config_sha256"),
            "adapter_id": None,
            "adapter_enabled": False,
            "prompt_id": VERSION,
            "generation": {"max_new_tokens": 1600, "do_sample": False},
        }

    def generate(self, payload):
        import torch

        medical = self.medical
        messages = [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {"scope": payload["scope"], "evidence": payload["evidence"]},
                    ensure_ascii=False,
                ),
            },
        ]
        inputs = medical.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        count = inputs["input_ids"].shape[-1]
        if count > medical.settings.max_input_tokens:
            raise ServiceError("INPUT_TOKEN_LIMIT", 413)
        if count + 1600 > min(
            medical.settings.max_context_tokens,
            medical.model.config.max_position_embeddings,
        ):
            raise ServiceError("CONTEXT_LIMIT", 413)
        inputs = {
            k: v.to(medical.model.get_input_embeddings().weight.device) for k, v in inputs.items()
        }
        torch.cuda.synchronize()
        started = time.perf_counter()
        # PEFT restores adapter state even when generation raises. The app owns
        # the same lock as Medical/Teaching until generation has actually stopped.
        with medical.model.disable_adapter(), torch.inference_mode():
            output = medical.model.generate(
                **inputs,
                max_new_tokens=1600,
                do_sample=False,
                pad_token_id=medical.tokenizer.pad_token_id,
                eos_token_id=medical.model.generation_config.eos_token_id,
            )
        torch.cuda.synchronize()
        tokens = output[0, count:]
        raw = medical.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        return Generation(raw, time.perf_counter() - started, count, tokens.numel())

    def close(self):
        pass  # Medical owns the shared weights/tokenizer and releases them once.
