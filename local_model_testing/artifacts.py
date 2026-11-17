"""Reject absent/unidentified adapters before importing GPU libraries."""

import sys
from pathlib import Path

from .common import ROOT, MODELS, REPORT, KINDS, file_hash, read


def check(kind):
    spec = KINDS[kind]
    manifest_path = MODELS / "locked-adapters.json"
    manifest = read(manifest_path) if manifest_path.exists() else {}
    entry = manifest.get(kind, {})
    adapter = Path(entry.get("adapter_path") or spec["adapter"])
    adapter = (adapter if adapter.is_absolute() else ROOT / adapter).resolve()
    for filename in ("adapter_config.json", "adapter_model.safetensors"):
        if not (adapter / filename).is_file():
            raise FileNotFoundError(
                f"{kind.upper()}_V1_ADAPTER_MISSING: {adapter / filename}"
            )
    config = read(adapter / "adapter_config.json")
    if (
        config.get("base_model_name_or_path") != spec["repo"]
        or config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
    ):
        raise ValueError("ADAPTER_IDENTITY_MISMATCH")
    if not entry.get("locked_v1_provenance"):
        raise ValueError(
            "LOCKED_V1_PROVENANCE_MISSING: supply the original approved artifact/run reference"
        )
    for filename, field in (
        ("adapter_config.json", "adapter_config_sha256"),
        ("adapter_model.safetensors", "adapter_sha256"),
    ):
        if not entry.get(field) or file_hash(adapter / filename) != entry[field]:
            raise ValueError("APPROVED_ADAPTER_HASH_MISSING_OR_MISMATCH: " + field)
    plan = read(REPORT / "download-plan.json")[kind]
    downloaded = read(REPORT / (kind + "-download.json"))
    if not downloaded.get("complete") or downloaded["revision"] != plan["revision"]:
        raise ValueError("BASE_DOWNLOAD_INCOMPLETE")
    base = MODELS / "base" / spec["name"]
    for item in downloaded["files"]:
        path = base / item["file"]
        if (
            not path.is_file()
            or path.stat().st_size != item["size"]
            or file_hash(path) != item["sha256"]
        ):
            raise ValueError("BASE_FILE_CHANGED: " + item["file"])
    return (
        base,
        adapter,
        {
            **entry,
            "base_revision": plan["revision"],
            "model_id": spec["repo"],
            "base_config_sha256": file_hash(base / "config.json"),
            "base_tokenizer_config_sha256": file_hash(base / "tokenizer_config.json"),
            "pilot_base_revision_match": plan["pilot_revision_match"],
        },
    )


if __name__ == "__main__":
    check(sys.argv[1])
    print("Local artifacts verified; this is not a model inference test.")
