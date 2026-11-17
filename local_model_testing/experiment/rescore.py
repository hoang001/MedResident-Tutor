"""Evaluate a new reference revision offline; old dataset, outputs and metrics are untouched."""
import argparse
import re
import sys
from pathlib import Path

from .common import DATA, ROOT, RUN, file_hash, rows, write
from .metrics import bootstrap, csv_write, medical_rows, summarize_medical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.revision) or args.revision == "medresident-benchmark-v1":
        raise ValueError("Use a distinct revision ID")
    reference = args.reference.resolve()
    if reference.is_relative_to(DATA.resolve()):
        raise ValueError("Do not edit the frozen reference directory; supply a new revision file")
    supplied = rows(reference)
    original = rows(DATA / "medical-reference.jsonl")
    assert {r["sample_id"] for r in supplied} == {r["sample_id"] for r in original}
    assert len(supplied) == len(original), "Duplicate/missing reference IDs"
    sys.path.insert(0, str(ROOT / "model-training"))
    from src.medical.validation import EvaluationRequest, validate_output
    import json

    inputs = {r["sample_id"]: r["payload"] for r in rows(DATA / "medical-inputs.jsonl")}
    for row in supplied:
        validate_output(json.dumps(row["expected"]), EvaluationRequest.model_validate(inputs[row["sample_id"]]))
    target = RUN / "offline-rescores" / args.revision
    target.mkdir(parents=True, exist_ok=False)
    result = {"reference_revision": args.revision, "reference_sha256": file_hash(reference),
              "original_manifest_sha256": file_hash(DATA / "manifest.json"), "inference_attempts": 0,
              "review_level": "Preserve supplied provenance; no automatic clinician approval",
              "medical": {}}
    for config in ("medical_base", "medical_adapter"):
        records = medical_rows(config, reference)
        result["medical"][config] = {**summarize_medical(records), "cluster_bootstrap_95_ci": bootstrap(records)}
        csv_write(target / (config+".csv"), records)
    write(target / "metrics.json", result)
    print(json.dumps({"rescore": str(target), "inference_attempts": 0}))


if __name__ == "__main__":
    main()
