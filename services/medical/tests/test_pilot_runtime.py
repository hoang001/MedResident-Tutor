import ast
import contextlib
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.medical import inference

from medical_service.config import Settings
from medical_service.runner import check_artifacts
from medical_service.validation import ServiceError

REPO = Path(__file__).resolve().parents[3]


def test_artifact_identity_without_loading_gpu(tmp_path):
    base, adapter = tmp_path / "base", tmp_path / "adapter"
    base.mkdir()
    adapter.mkdir()
    config = b'{"model_type":"qwen3"}'
    (base / "config.json").write_bytes(config)
    (base / "tokenizer_config.json").write_text("{}")
    (base / "model.safetensors").write_bytes(b"synthetic-base-not-real-weights")
    weights = b"synthetic-adapter-not-real-weights"
    (adapter / "adapter_model.safetensors").write_bytes(weights)
    adapter_config = {
        "base_model_name_or_path": inference.MODEL_ID,
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
    }
    (adapter / "adapter_config.json").write_text(json.dumps(adapter_config))
    settings = Settings(
        base,
        adapter,
        hashlib.sha256(weights).hexdigest(),
        hashlib.sha256(config).hexdigest(),
        "synthetic-api-key-123",
        hashlib.sha256((adapter / "adapter_config.json").read_bytes()).hexdigest(),
    )
    metadata = check_artifacts(settings)
    assert metadata["generation"] == {
        "max_new_tokens": 1200,
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "top_k": None,
    }
    assert metadata["model_id"] == "Qwen/Qwen3-4B-Instruct-2507"
    (adapter / "adapter_model.safetensors").write_bytes(b"different")
    with pytest.raises(ServiceError, match="ADAPTER_HASH_MISMATCH"):
        check_artifacts(settings)
    (adapter / "adapter_model.safetensors").write_bytes(weights)
    adapter_config["base_model_name_or_path"] = "some-other-model"
    (adapter / "adapter_config.json").write_text(json.dumps(adapter_config))
    with pytest.raises(ServiceError, match="ADAPTER_CONFIG_HASH_MISMATCH"):
        check_artifacts(settings)
    from dataclasses import replace

    settings = replace(
        settings,
        adapter_config_sha256=hashlib.sha256(
            (adapter / "adapter_config.json").read_bytes()
        ).hexdigest(),
    )
    with pytest.raises(ServiceError, match="ADAPTER_IDENTITY_MISMATCH"):
        check_artifacts(settings)
    (adapter / "adapter_model.safetensors").unlink()
    with pytest.raises(ServiceError, match="ADAPTER_WEIGHTS_MISSING"):
        check_artifacts(settings)


class Tensor:
    shape = (1, 10)

    def to(self, _device):
        return self

    def numel(self):
        return 3


class Tokenizer:
    pad_token_id = 0

    def apply_chat_template(self, messages, **kwargs):
        self.messages, self.kwargs = messages, kwargs
        return {"input_ids": Tensor()}

    def decode(self, tokens, **kwargs):
        return ' {"example":true} '


class Model:
    config = SimpleNamespace(max_position_embeddings=2048)
    generation_config = SimpleNamespace(eos_token_id=99)

    def __init__(self):
        self.calls = 0

    def get_input_embeddings(self):
        return SimpleNamespace(weight=SimpleNamespace(device="synthetic-device"))

    def generate(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs

        class Output:
            def __getitem__(self, key):
                assert key[0] == 0 and key[1].start == 10
                return Tensor()

        return Output()


def test_exact_generation_kwargs_and_no_silent_truncation(monkeypatch):
    # Stub the torch import; never import/install torch or use a GPU in this test.
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=contextlib.nullcontext)
    )
    tokenizer, model = Tokenizer(), Model()
    messages = [
        {"role": "system", "content": "synthetic"},
        {"role": "user", "content": "synthetic"},
    ]
    raw, elapsed, inputs, tokens = inference.generate_text(
        messages, tokenizer, model, max_input_tokens=20, max_context_tokens=2048
    )
    assert raw == '{"example":true}' and elapsed >= 0 and (inputs, tokens) == (10, 3)
    assert tokenizer.messages == messages
    assert tokenizer.kwargs == {
        "tokenize": True,
        "add_generation_prompt": True,
        "return_dict": True,
        "return_tensors": "pt",
    }
    assert {k: v for k, v in model.kwargs.items() if k != "input_ids"} == {
        "max_new_tokens": 1200,
        "do_sample": False,
        "pad_token_id": 0,
        "eos_token_id": 99,
    }
    with pytest.raises(ValueError, match="INPUT_TOKEN_LIMIT"):
        inference.generate_text(messages, tokenizer, model, max_input_tokens=9)
    with pytest.raises(ValueError, match="CONTEXT_LIMIT"):
        inference.generate_text(messages, tokenizer, model, max_context_tokens=1209)
    assert model.calls == 1


def test_baseline_wrapper_keeps_offline_metrics_without_io():
    path = REPO / "model-training/src/medical/evaluate_baseline.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_sample"
    )
    namespace = {
        "json": json,
        "generate_text": lambda *_: ('{"sample":true}', 0.5, 10, 7),
        "extract_json": inference.extract_json,
        "validate_contract": lambda _: [],
        "compare_with_gold": lambda *_: {"synthetic": True},
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    result = namespace["run_sample"](
        {
            "sample_id": "fake",
            "question_id": "fake",
            "messages": [
                {"role": "user", "content": "fake"},
                {"role": "assistant", "content": "{}"},
            ],
        },
        None,
        None,
    )
    assert result["generated_tokens"] == 7 and result["contract_valid"] is True


def test_shared_module_has_no_model_or_dataset_imports():
    source = Path(inference.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(
        isinstance(n, ast.Import) and any(x.name == "torch" for x in n.names) for n in tree.body
    )
    assert "mkdir" not in source and "read_jsonl" not in source


def test_loader_uses_pilot_quantization_and_local_files_only(monkeypatch, tmp_path):
    captured = {}
    torch = SimpleNamespace(float16="synthetic-float16")
    tokenizer = SimpleNamespace(pad_token_id=None, eos_token="EOS")
    model = SimpleNamespace(generation_config=SimpleNamespace(), eval=lambda: None)

    def token_load(path, **kwargs):
        captured["tokenizer"] = (path, kwargs)
        return tokenizer

    def model_load(path, **kwargs):
        captured["model"] = (path, kwargs)
        return model

    def quant(**kwargs):
        captured["quantization"] = kwargs
        return "synthetic-quantization"

    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=token_load),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=model_load),
            BitsAndBytesConfig=quant,
        ),
    )
    loaded_tokenizer, loaded_model = inference.load_model(tmp_path, local_files_only=True)
    assert loaded_tokenizer is tokenizer and loaded_model is model
    assert captured["quantization"] == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "synthetic-float16",
        "bnb_4bit_use_double_quant": True,
    }
    assert captured["model"] == (
        str(tmp_path),
        {
            "local_files_only": True,
            "quantization_config": "synthetic-quantization",
            "device_map": {"": 0},
            "dtype": "synthetic-float16",
            "low_cpu_mem_usage": True,
            "trust_remote_code": True,
        },
    )
    assert captured["tokenizer"] == (
        str(tmp_path),
        {"local_files_only": True, "trust_remote_code": True},
    )
    assert tokenizer.pad_token == "EOS"
    assert vars(model.generation_config) == {
        "do_sample": False,
        "temperature": None,
        "top_p": None,
        "top_k": None,
    }
