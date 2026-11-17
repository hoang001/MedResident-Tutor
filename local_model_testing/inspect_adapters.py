"""Inspect the user-supplied artifacts and create an isolated integration run.

User provenance is recorded honestly; a newly computed hash is not historical proof.
No GPU/model import, training, locked benchmark or external inference.
"""

import json
import shutil
import struct
import subprocess
from datetime import UTC, datetime

from .common import (
    ROOT,
    MODELS,
    REPORT_BASE,
    KINDS,
    file_hash,
    read,
    write,
    system_snapshot,
)


def inspect(kind, relative):
    folder = ROOT / relative
    spec = KINDS[kind]
    base = MODELS / "base" / spec["name"]
    config = read(folder / "adapter_config.json")
    assert config["base_model_name_or_path"] == spec["repo"]
    assert config["peft_type"] == "LORA" and config["task_type"] == "CAUSAL_LM"
    assert (
        config["r"] == 16
        and config["lora_alpha"] == 32
        and config["lora_dropout"] == 0.05
    )
    targets = {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "up_proj",
        "gate_proj",
        "down_proj",
    }
    assert set(config["target_modules"]) == targets
    weights = folder / "adapter_model.safetensors"
    with weights.open("rb") as stream:
        header_size = struct.unpack("<Q", stream.read(8))[0]
        assert header_size < 10 * 1024**2
        header = json.loads(stream.read(header_size))
    tensors = {k: v for k, v in header.items() if k != "__metadata__"}
    bc = read(base / "config.json")
    hidden, inter, heads, kv = (
        bc[k]
        for k in (
            "hidden_size",
            "intermediate_size",
            "num_attention_heads",
            "num_key_value_heads",
        )
    )
    head = bc.get("head_dim", hidden // heads)
    shapes = {
        "down_proj": (inter, hidden),
        "up_proj": (hidden, inter),
        "gate_proj": (hidden, inter),
        "q_proj": (hidden, heads * head),
        "k_proj": (hidden, kv * head),
        "v_proj": (hidden, kv * head),
        "o_proj": (heads * head, hidden),
    }
    expected = set()
    for layer in range(bc["num_hidden_layers"]):
        for module, (size_in, size_out) in shapes.items():
            for side, shape in (("A", [16, size_in]), ("B", [size_out, 16])):
                name = f"base_model.model.model.layers.{layer}.{'mlp' if module in {'down_proj', 'up_proj', 'gate_proj'} else 'self_attn'}.{module}.lora_{side}.weight"
                assert (
                    tensors[name]["shape"] == shape and tensors[name]["dtype"] == "F32"
                ), name
                expected.add(name)
    assert expected == set(tensors)
    assert (
        max(t["data_offsets"][1] for t in tensors.values()) + header_size + 8
        == weights.stat().st_size
    )
    a, b = read(folder / "tokenizer.json"), read(base / "tokenizer.json")
    for value in (a, b):
        model = value["model"]
        model["merges"] = [
            tuple(x.split(" ")) if isinstance(x, str) else tuple(x)
            for x in model["merges"]
        ]
        model.setdefault("ignore_merges", False)
    assert a == b, "Tokenizer has semantic changes beyond save format"
    base_tc = read(base / "tokenizer_config.json")
    assert (folder / "chat_template.jinja").read_text(encoding="utf-8") == base_tc[
        "chat_template"
    ]
    row = {
        "adapter_path": relative,
        "adapter_sha256": file_hash(weights),
        "adapter_config_sha256": file_hash(folder / "adapter_config.json"),
        "locked_v1_provenance": "User supplied these artifacts in adapter/ in direct response to request for locked V1 adapters, 2026-11-09; independently checked architecture/config/tokenizer, not an independent historical hash certificate",
        "historical_weight_hash_available": False,
        "tokenizer_policy": "Use verified base tokenizer and original chat template; adapter save-format differences normalized for inspection only",
    }
    audit = {
        **row,
        "model_id": spec["repo"],
        "weights_bytes": weights.stat().st_size,
        "tensor_count": len(tensors),
        "tensor_shapes_checked": True,
        "tokenizer_semantics_and_chat_template_match": True,
        "base_commit_of_original_training": "not_recorded_in_supplied_adapter_config",
    }
    if kind == "teaching":
        summary = read(folder.parent / "training_summary.json")
        state = read(folder.parent / "trainer_state.json")
        assert summary["model_id"] == spec["repo"] and summary["smoke_test"] is False
        assert state["global_step"] == summary["successful_optimizer_steps"] == 15
        audit["supplied_training_report"] = {
            k: summary[k]
            for k in (
                "model_id",
                "smoke_test",
                "train_samples",
                "validation_samples",
                "successful_optimizer_steps",
                "trainable_params",
                "torch_version",
            )
        }
        audit["training_summary_sha256"] = file_hash(
            folder.parent / "training_summary.json"
        )
        row["training_summary_sha256"] = audit["training_summary_sha256"]
    return row, audit


def main():
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = REPORT_BASE / "runs" / run_id
    report.mkdir(parents=True, exist_ok=False)
    manifest, audits = {}, {}
    for kind, relative in (
        ("medical", "adapter/adapter"),
        ("teaching", "adapter/teaching-qwen2.5-v1/adapter"),
    ):
        manifest[kind], audits[kind] = inspect(kind, relative)
    path = MODELS / "locked-adapters.json"
    if path.exists():
        shutil.copy2(path, report / "previous-locked-adapters.json")
    write(path, manifest)
    write(report / "adapter-inspection.json", audits)
    for name in (
        "download-plan.json",
        "medical-download.json",
        "teaching-download.json",
        "runtime-probe.json",
        "integration-inputs.json",
    ):
        shutil.copy2(REPORT_BASE / name, report / name)
    for name in ("inputs", "expected"):
        shutil.copytree(REPORT_BASE / name, report / name)
    baseline = system_snapshot()
    exe = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
    baseline["services"] = subprocess.check_output(
        [exe, "ps", "--format", "{{.Names}} {{.Ports}}"], text=True
    ).splitlines()
    baseline["provider"] = subprocess.check_output(
        [
            exe,
            "exec",
            "medresident-tutor-backend-1",
            "python",
            "-c",
            "import json; from app.core.config import get_settings; c=get_settings(); print(json.dumps(dict(app_env=c.app_env,practice_provider=c.practice_provider,model_calls_enabled=c.model_calls_enabled)))",
        ],
        text=True,
    ).strip()
    write(report / "baseline.json", baseline)
    protected = {
        p.relative_to(ROOT).as_posix(): file_hash(p)
        for directory in (
            "model-training/src",
            "model-training/configs",
            "model-training/prepared-data",
            "data/training",
            "data/integration",
        )
        for p in (ROOT / directory).rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".jsonl", ".txt"}
    }
    write(report / "protected-file-hashes.json", protected)
    write(
        REPORT_BASE / "active-run.json",
        {"run_id": run_id, "report_directory": str(report)},
    )
    print("RUN_ID", run_id)
    print(
        "Adapter configs, tensors and tokenizer semantics match both base models. Historical adapter hashes unavailable; user-supplied provenance recorded."
    )
    print("RAM_FREE_GIB", round(baseline["system"]["ram_available_bytes"] / 1024**3, 2))


if __name__ == "__main__":
    main()
