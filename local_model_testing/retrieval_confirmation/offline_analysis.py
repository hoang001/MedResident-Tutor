"""Recompute the existing benchmark offline; never calls metrics.main or a model."""

import json
from collections import Counter

from local_model_testing.experiment import metrics as old_metrics
from local_model_testing.experiment.retrieval import coverage
from local_model_testing.experiment.worker import parse

from .common import ROOT, RUN, PARENT, read, write, rows, digest, file_hash

DATA = ROOT / "data/evaluation/medresident-benchmark-v1"
OUT = RUN / "offline"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = read(DATA / "manifest.json")
    assert all(file_hash(DATA / name) == sha for name, sha in manifest["files"].items())
    old_metrics.RUN = PARENT
    old_metrics.DATA = DATA
    references = {r["sample_id"]: r for r in rows(DATA / "medical-reference.jsonl")}
    inputs = {
        r["sample_id"]: r
        for r in rows(DATA / "medical-inputs.jsonl")
        if r["split"] == "test"
    }
    medical, grouped, revalidation, input_checks = [], [], [], []
    summaries = {}
    for config in ("medical_base", "medical_adapter"):
        records = old_metrics.medical_rows(config)
        assert {r["sample_id"] for r in records} == set(inputs)
        for r in records:
            sid = r["sample_id"]
            output = read(PARENT / config / (sid + ".json"))
            payload = inputs[sid]["payload"]
            raw_path = PARENT / config / "raw" / (sid + ".json")
            check = {
                "config": config,
                "sample_id": sid,
                "raw_available": raw_path.exists(),
            }
            if raw_path.exists():
                reproduced = parse("medical", payload, read(raw_path)["text"])
                check.update(
                    schema_flag_matches=reproduced["schema_valid"]
                    == output["schema_valid"],
                    contract_flag_matches=reproduced["contract_valid"]
                    == output["contract_valid"],
                    parsed_matches=reproduced.get("parsed") == output.get("parsed"),
                )
                assert all(
                    check[k]
                    for k in (
                        "schema_flag_matches",
                        "contract_flag_matches",
                        "parsed_matches",
                    )
                )
            revalidation.append(check)
            hashed = output.get("payload_sha256")
            input_checks.append(
                {
                    "config": config,
                    "sample_id": sid,
                    "canonical_payload_sha256": digest(payload),
                    "observed_payload_sha256": hashed,
                    "match": hashed == digest(payload) if hashed else None,
                }
            )
            assert not hashed or hashed == digest(payload)
            expected = references[sid]["expected"]
            pred = output.get("parsed") if output.get("contract_valid") else None
            by_id = (
                {c["criterion_id"]: c["score"] for c in pred["rubric_scores"]}
                if pred
                else {}
            )
            r["criterion_vector_by_id_agreement"] = bool(pred) and all(
                by_id.get(c["criterion_id"]) == c["score"]
                for c in expected["rubric_scores"]
            )
            r["total_correct_vector_wrong"] = (
                r["total_agreement"] and not r["criterion_vector_by_id_agreement"]
            )
            medical.append(r)
        summary = old_metrics.summarize_medical(records)
        summary.update(
            criterion_vector_by_id_agreement=sum(
                r["criterion_vector_by_id_agreement"] for r in records
            )
            / len(records),
            total_correct_vector_wrong=sum(
                r["total_correct_vector_wrong"] for r in records
            ),
        )
        summaries[config] = summary
        for dimension in ("topic", "answer_type"):
            for value in sorted({r[dimension] for r in records}):
                group = [r for r in records if r[dimension] == value]
                grouped.append(
                    {
                        "config": config,
                        "dimension": dimension,
                        "group": value,
                        **old_metrics.summarize_medical(group),
                    }
                )
    base = [r for r in medical if r["config"] == "medical_base"]
    adapter = [r for r in medical if r["config"] == "medical_adapter"]
    paired = []
    for b, a in zip(base, adapter):
        assert b["sample_id"] == a["sample_id"]
        sid = b["sample_id"]
        cb, ca = [
            read(PARENT / c / (sid + ".json"))
            for c in ("medical_base", "medical_adapter")
        ]
        paired.append(
            {
                "sample_id": sid,
                "topic": b["topic"],
                "answer_type": b["answer_type"],
                "base_correct": b["total_agreement"],
                "adapter_correct": a["total_agreement"],
                "base_contract_valid": b["contract_valid"],
                "adapter_contract_valid": a["contract_valid"],
                "actual_prompt_hash_same": cb.get("actual_prompt_sha256")
                == ca.get("actual_prompt_sha256")
                if cb.get("actual_prompt_sha256") and ca.get("actual_prompt_sha256")
                else None,
                "shared_payload_sha256": digest(inputs[sid]["payload"]),
                "shared_rubric_sha256": digest(inputs[sid]["payload"]["rubric"]),
                "shared_evidence_sha256": digest(inputs[sid]["payload"]["evidence"]),
                "shared_expected_sha256": digest(references[sid]["expected"]),
            }
        )
    metas = {
        c: read(PARENT / (c + "-process.json"))["metadata"]
        for c in ("medical_base", "medical_adapter")
    }
    meta_diffs = {
        k: [metas["medical_base"].get(k), metas["medical_adapter"].get(k)]
        for k in set(metas["medical_base"]) | set(metas["medical_adapter"])
        if metas["medical_base"].get(k) != metas["medical_adapter"].get(k)
    }
    assert set(meta_diffs) == {"adapter_enabled", "adapter_sha256"}
    old = read(PARENT / "metrics.json")
    comparisons = []
    for config, summary in summaries.items():
        for key in old["medical"][config]:
            if key in summary:
                assert summary[key] == old["medical"][config][key], (config, key)
        comparisons.append({"config": config, "original_metrics_reproduced": True})
    teaching, teaching_summary, teaching_validation = [], {}, []
    t_inputs = {
        r["sample_id"]: r
        for r in rows(DATA / "teaching-inputs.jsonl")
        if r["split"] == "test"
    }
    for config in ("teaching_base", "teaching_adapter"):
        records = old_metrics.teaching_rows(config)
        teaching.extend(records)
        summary = old_metrics.summarize_teaching(records)
        assert summary == old["teaching"][config]
        teaching_summary[config] = summary
        for sid, sample in t_inputs.items():
            checkpoint = read(PARENT / config / (sid + ".json"))
            assert checkpoint.get("payload_sha256") == digest(sample["payload"])
            reproduced = parse(
                "teaching",
                sample["payload"],
                read(PARENT / config / "raw" / (sid + ".json"))["text"],
            )
            assert all(
                reproduced.get(k) == checkpoint.get(k)
                for k in (
                    "parsed",
                    "schema_valid",
                    "contract_valid",
                    "raw_proxy",
                    "guarded",
                    "guarded_proxy",
                )
            )
            teaching_validation.append(
                {
                    "config": config,
                    "sample_id": sid,
                    "raw_parsed_guarded_proxies_reproduced": True,
                    "payload_sha256_matches": True,
                }
            )
    retrieval = read(PARENT / "retrieval.json")
    provenance = {r["question_id"]: r for r in rows(DATA / "provenance.jsonl")}
    retrieval_rows, retrieval_summary = [], {}
    for saved in retrieval["records"]:
        cov = coverage(saved["retrieved"], provenance[saved["question_id"]])
        assert cov["hit_at_5"] == saved["hit_at_5"]
        assert (
            abs(
                cov["strict_source_span_coverage"]
                - saved["strict_source_span_coverage"]
            )
            < 1e-9
        )
        assert (
            float(cov["strict_source_span_coverage"] >= 1 - 1e-9)
            == saved["criterion_evidence_coverage_proxy"]
        )
        retrieval_rows.append(
            {
                k: saved[k]
                for k in [
                    "mode",
                    "question_id",
                    "topic",
                    "hit_at_5",
                    "criterion_evidence_coverage_proxy",
                    "semantic_criterion_coverage",
                    "latency_seconds",
                ]
            }
        )
    for mode in ("vector", "hybrid"):
        group = [r for r in retrieval_rows if r["mode"] == mode]
        retrieval_summary[mode] = {
            "queries": len(group),
            "hit_at_5": sum(r["hit_at_5"] for r in group) / len(group),
            "criterion_evidence_coverage_proxy": sum(
                r["criterion_evidence_coverage_proxy"] for r in group
            )
            / len(group),
            "semantic_criterion_coverage": None,
            "latency_median_seconds": old_metrics.percentile(
                [r["latency_seconds"] for r in group], 50
            ),
            "latency_p95_seconds": old_metrics.percentile(
                [r["latency_seconds"] for r in group], 95
            ),
        }
        for key, value in retrieval_summary[mode].items():
            previous = retrieval["metrics"][mode][key]
            assert value == previous or (
                isinstance(value, float) and abs(value - previous) < 1e-12
            )
    reviews = rows(PARENT / "manual-review.jsonl")
    content_errors = [
        r
        for r in reviews
        if any(
            r.get(k) is True
            for k in read(PARENT / "review-protocol.json")["medical_flags"]
        )
        or r.get("role_violation") is True
    ]
    error_examples = []
    for review in content_errors:
        config, sid = review["config"], review["sample_id"]
        if config.startswith("medical"):
            sample = inputs.get(sid)
            if not sample:
                continue
            output = read(PARENT / config / (sid + ".json"))
            expected = references[sid]["expected"]
            error_examples.append(
                {
                    "config": config,
                    "sample_id": sid,
                    "student_answer": sample["payload"]["student_answer"],
                    "rubric": sample["payload"]["rubric"],
                    "evidence": sample["payload"]["evidence"],
                    "parsed": output.get("parsed"),
                    "expected": expected,
                    "review": review,
                    "total_matches_despite_content_issue": bool(
                        output.get("contract_valid")
                    )
                    and output["parsed"]["total_score"] == expected["total_score"],
                }
            )
    runtime = {}
    for config in (
        "medical_base",
        "medical_adapter",
        "teaching_base",
        "teaching_adapter",
    ):
        process = read(PARENT / (config + "-process.json"))
        runtime[config] = {
            k: process.get(k)
            for k in [
                "load_and_artifact_check_seconds",
                "peak_vram_allocated_bytes",
                "peak_vram_reserved_bytes",
                "peak_process_rss_bytes",
                "total_wall_seconds",
            ]
        }
        runtime[config]["metadata"] = process["metadata"]
        runtime[config]["segment_scope_note"] = (
            "Latest saved process segment; interruption/recovery segments remain separate"
        )
    result = {
        "revision": "offline-verification-v1",
        "no_inference": True,
        "source_run": PARENT.relative_to(ROOT).as_posix(),
        "source_manifest_sha256": file_hash(DATA / "manifest.json"),
        "source_metrics_sha256": file_hash(PARENT / "metrics.json"),
        "medical": summaries,
        "medical_paired": old_metrics.paired_bootstrap(base, adapter),
        "paired_outcomes": dict(
            Counter(
                f"base_{int(r['base_correct'])}_adapter_{int(r['adapter_correct'])}"
                for r in paired
            )
        ),
        "metadata_differences": meta_diffs,
        "same_sample_ids": True,
        "actual_prompt_comparisons": dict(
            Counter(str(r["actual_prompt_hash_same"]) for r in paired)
        ),
        "input_payload_comparisons": dict(
            Counter(str(r["match"]) for r in input_checks)
        ),
        "raw_revalidated": sum(r["raw_available"] for r in revalidation),
        "raw_unavailable": sum(not r["raw_available"] for r in revalidation),
        "teaching": teaching_summary,
        "teaching_raw_revalidated": len(teaching_validation),
        "retrieval": retrieval_summary,
        "retrieval_configuration": retrieval["configuration"],
        "runtime": runtime,
        "manual_review_original": old["review"],
        "leakage_audit": read(DATA / "leakage-audit.json"),
        "original_metrics_reproduction": comparisons,
        "vector_by_id_revision_differences": [
            {"config": r["config"], "sample_id": r["sample_id"]}
            for r in medical
            if r["vector_agreement"] != r["criterion_vector_by_id_agreement"]
        ],
    }
    write(OUT / "benchmark-verification.json", result)
    write(OUT / "medical-raw-revalidation.json", revalidation)
    write(OUT / "input-identity-checks.json", input_checks)
    write(OUT / "teaching-revalidation.json", teaching_validation)
    write(OUT / "content-error-examples.json", error_examples)
    for name, records in [
        ("medical-per-sample", medical),
        ("medical-by-group", grouped),
        ("medical-paired", paired),
        ("teaching-per-sample", teaching),
        ("retrieval-per-question", retrieval_rows),
        ("medical-summary", [{"config": c, **m} for c, m in summaries.items()]),
        (
            "teaching-summary",
            [
                {"config": c, "stage": s, **m}
                for c, stages in teaching_summary.items()
                for s, m in stages.items()
            ],
        ),
        (
            "retrieval-summary",
            [{"mode": mode, **m} for mode, m in retrieval_summary.items()],
        ),
    ]:
        old_metrics.csv_write(OUT / (name + ".csv"), records)
    print(
        json.dumps(
            {
                "medical": summaries,
                "paired": result["paired_outcomes"],
                "verified_raw": result["raw_revalidated"],
                "teaching_raw": len(teaching_validation),
                "retrieval": retrieval_summary,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
