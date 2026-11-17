"""Metrics from saved outputs only. Errors stay in the declared test denominator."""
import csv
import json
from collections import Counter
from datetime import datetime

from . import ledger
from .common import DATA, RUN, frozen, read, rows, write


def rate(numerator, denominator):
    return numerator/denominator if denominator else None


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    position = (len(values)-1)*p/100
    left = int(position)
    return values[left] + (values[min(left+1, len(values)-1)]-values[left])*(position-left)


def medical_rows(config, reference_path=None):
    reference = {r["sample_id"]: r for r in rows(reference_path or DATA / "medical-reference.jsonl")}
    result = []
    for sample in rows(DATA / "medical-inputs.jsonl"):
        if sample["split"] != "test":
            continue
        path = RUN / config / (sample["sample_id"] + ".json")
        output = read(path) if path.exists() else {}
        gold = reference[sample["sample_id"]]
        expected = gold["expected"]
        valid = bool(output.get("contract_valid"))
        prediction = output.get("parsed") if valid else None
        expected_vector = [c["score"] for c in expected["rubric_scores"]]
        vector = [c["score"] for c in prediction["rubric_scores"]] if valid else None
        wrong_ids = set(gold["explicitly_wrong_criteria"])
        valid_wrong = sum(c["criterion_id"] in wrong_ids for c in prediction["rubric_scores"]) if valid else 0
        overaward = sum(c["criterion_id"] in wrong_ids and c["score"] > 0 for c in prediction["rubric_scores"]) if valid else 0
        result.append({"config": config, "sample_id": sample["sample_id"],
            "question_id": sample["question_id"], "topic": sample["topic"],
            "answer_type": sample["answer_type"], "attempted": path.exists(),
            "schema_valid": bool(output.get("schema_valid")), "contract_valid": valid,
            "total_agreement": valid and prediction["total_score"] == expected["total_score"],
            "vector_agreement": valid and vector == expected_vector,
            "normalized_absolute_error": abs(prediction["total_score"]-expected["total_score"])/expected["max_score"] if valid else None,
            "wrong_criteria_planned": len(wrong_ids), "wrong_criteria_valid": valid_wrong,
            "wrong_criteria_awarded": overaward, "expected_total": expected["total_score"],
            "predicted_total": prediction["total_score"] if valid else None,
            "expected_vector": expected_vector, "predicted_vector": vector,
            "sufficient_evidence_agreement": valid and prediction["sufficient_evidence"] == expected["sufficient_evidence"],
            "error_type": output.get("error", {}).get("type", "not_run" if not path.exists() else None),
            "error_code": output.get("error", {}).get("code"),
            "truncated": bool(output.get("truncated")),
            "generation_seconds": output.get("generation_seconds"),
            "input_tokens": output.get("input_tokens", 0), "generated_tokens": output.get("generated_tokens", 0)})
    return result


def summarize_medical(records):
    count = len(records)
    attempted = sum(r["attempted"] for r in records)
    valid = [r for r in records if r["contract_valid"]]
    errors = [r["normalized_absolute_error"] for r in valid]
    timings = [r["generation_seconds"] for r in records if r["generation_seconds"] is not None]
    wrong_denominator = sum(r["wrong_criteria_valid"] for r in records)
    wrong_planned = sum(r["wrong_criteria_planned"] for r in records)
    return {"planned": count, "attempted": attempted, "contract_valid": len(valid),
        "failed_attempts": attempted-len(valid), "not_run": count-attempted,
        "schema_valid": sum(r["schema_valid"] for r in records),
        "schema_valid_rate_all_planned": rate(sum(r["schema_valid"] for r in records), count),
        "schema_valid_rate_attempted": rate(sum(r["schema_valid"] for r in records), attempted),
        "exact_total_score_agreement": rate(sum(r["total_agreement"] for r in records), count),
        "exact_criterion_vector_agreement": rate(sum(r["vector_agreement"] for r in records), count),
        "mae_normalized": sum(errors)/len(errors) if errors else None,
        "mae_coverage": rate(len(valid), count), "mae_n": len(valid),
        "wrong_criterion_award_rate": rate(sum(r["wrong_criteria_awarded"] for r in records), wrong_denominator),
        "wrong_criterion_awards": sum(r["wrong_criteria_awarded"] for r in records),
        "wrong_criteria_scored_denominator": wrong_denominator,
        "wrong_criteria_planned": wrong_planned,
        "wrong_criterion_coverage": rate(wrong_denominator, wrong_planned),
        "sufficient_evidence_agreement": rate(sum(r["sufficient_evidence_agreement"] for r in records), count),
        "generation_latency_median_seconds": percentile(timings, 50),
        "generation_latency_p95_seconds": percentile(timings, 95),
        "input_tokens": sum(r["input_tokens"] for r in records),
        "generated_tokens": sum(r["generated_tokens"] for r in records),
        "truncated": sum(r["truncated"] for r in records),
        "transport_errors": None,
        "transport_scope": "Standalone local batch; HTTP transport not evaluated",
        "error_codes": dict(Counter(r["error_code"] for r in records if r.get("error_code"))),
        "error_types": dict(Counter(r["error_type"] for r in records if r["error_type"]))}


def bootstrap(records):
    """Resample eight chapter/topic clusters, keeping all questions/variants together."""
    import random
    topics = sorted({r["topic"] for r in records})
    rng = random.Random(42)
    estimates = {"total_agreement": [], "vector_agreement": []}
    for _ in range(1000):
        draws = rng.choices(topics, k=len(topics))
        sample = [r for topic in draws for r in records if r["topic"] == topic]
        for key in estimates:
            estimates[key].append(sum(r[key] for r in sample)/len(sample))
    return {"method": "1000 percentile resamples of topic/chapter clusters, seed42; variants never independent",
            "clusters": len(topics), **{key: [percentile(values, 2.5), percentile(values, 97.5)]
                                         for key, values in estimates.items()}}


def paired_bootstrap(base, adapter):
    """A/B difference with paired resampling of whole topic clusters."""
    import random
    assert [r["sample_id"] for r in base] == [r["sample_id"] for r in adapter]
    assert [r["topic"] for r in base] == [r["topic"] for r in adapter]
    topics = sorted({r["topic"] for r in base})
    rng = random.Random(42)
    results = {}
    for key in ("total_agreement", "vector_agreement"):
        differences = [(a["topic"], int(b[key])-int(a[key])) for a, b in zip(base, adapter)]
        values = []
        for _ in range(1000):
            sample = [delta for topic in rng.choices(topics, k=len(topics))
                      for group, delta in differences if group == topic]
            values.append(sum(sample)/len(sample))
        results[key] = {"adapter_minus_base": sum(d for _, d in differences)/len(differences),
                        "cluster_bootstrap_95_ci": [percentile(values, 2.5), percentile(values, 97.5)]}
    return {"method": "paired A/B; 1000 topic-cluster resamples, seed42; all variants kept together",
            "clusters": len(topics), "metrics": results}


def teaching_rows(config):
    result = []
    for sample in rows(DATA / "teaching-inputs.jsonl"):
        if sample["split"] != "test":
            continue
        path = RUN / config / (sample["sample_id"] + ".json")
        output = read(path) if path.exists() else {}
        derived_error_type = output.get("error", {}).get("type")
        if derived_error_type == "parse_or_schema":
            derived_error_type = "schema" if output.get("raw_proxy", {}).get("json_valid") else "parse"
        for stage in ("raw", "guarded"):
            prediction = output.get("parsed" if stage == "raw" else "guarded")
            proxy = output.get(stage + "_proxy", {})
            result.append({"config": config, "stage": stage, "sample_id": sample["sample_id"],
                "question_id": sample["question_id"], "topic": sample["topic"],
                "context_type": sample["context_type"], "attempted": path.exists(),
                "schema_valid": bool(output.get("schema_valid")) and prediction is not None,
                "alignment_proxy_pass": bool(proxy) and all(proxy.values()),
                "context_proxy_pass": proxy.get("learner_context_usage", False) if sample["context_type"] != "none" else None,
                "forbidden_score_keys_proxy_pass": proxy.get("forbidden_score_fields", False),
                "anchor_proxy_pass": proxy.get("medical_anchor_guard", False),
                "proxy": proxy, "truncated": bool(output.get("truncated")),
                "error_type_derived": derived_error_type,
                "generation_seconds": output.get("generation_seconds"),
                "input_tokens": output.get("input_tokens", 0),
                "generated_tokens": output.get("generated_tokens", 0)})
    return result


def summarize_teaching(records):
    result = {}
    for stage in ("raw", "guarded"):
        group = [r for r in records if r["stage"] == stage]
        context = [r for r in group if r["context_type"] != "none"]
        timings = [r["generation_seconds"] for r in group if r["generation_seconds"] is not None]
        result[stage] = {"planned": len(group), "attempted": sum(r["attempted"] for r in group),
            "schema_valid_rate": rate(sum(r["schema_valid"] for r in group), len(group)),
            "alignment_proxy_pass_rate": rate(sum(r["alignment_proxy_pass"] for r in group), len(group)),
            "context_usage_proxy_pass_rate": rate(sum(r["context_proxy_pass"] for r in context), len(context)),
            "context_denominator": len(context),
            "forbidden_score_keys_proxy_pass_rate": rate(sum(r["forbidden_score_keys_proxy_pass"] for r in group), len(group)),
            "medical_anchor_proxy_pass_rate": rate(sum(r["anchor_proxy_pass"] for r in group), len(group)),
            "truncated": sum(r["truncated"] for r in group),
            "generation_latency_median_seconds": percentile(timings, 50),
            "generation_latency_p95_seconds": percentile(timings, 95),
            "input_tokens": sum(r["input_tokens"] for r in group),
            "generated_tokens": sum(r["generated_tokens"] for r in group),
            "error_types": dict(Counter(r["error_type_derived"] for r in group if r["error_type_derived"])),
            "proxy_warning": "Automated lexical/alignment proxies only; semantic role violations and pedagogy require direct review"}
    return result


def csv_write(path, values):
    if not values:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        for row in values:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def review_measure(records, key, non_applicable_ids=None):
    non_applicable_ids = non_applicable_ids or set()
    applicable = [r for r in records if r["sample_id"] not in non_applicable_ids]
    known = [r[key] for r in applicable if r.get(key) is not None]
    return {"n_known": len(known), "n_unknown": len(applicable)-len(known),
            "n_not_applicable": len(records)-len(applicable),
            "mean_or_rate": sum(known)/len(known) if known else None}


def main():
    frozen()
    summary = {"medical": {}, "teaching": {}, "runtime": {}, "review": {}}
    all_medical, all_teaching = [], []
    for config in ("medical_base", "medical_adapter"):
        records = medical_rows(config)
        all_medical.extend(records)
        summary["medical"][config] = {**summarize_medical(records), "cluster_bootstrap_95_ci": bootstrap(records)}
    for config in ("teaching_base", "teaching_adapter"):
        records = teaching_rows(config)
        all_teaching.extend(records)
        summary["teaching"][config] = summarize_teaching(records)
    summary["medical_paired_comparison"] = paired_bootstrap(
        [r for r in all_medical if r["config"] == "medical_base"],
        [r for r in all_medical if r["config"] == "medical_adapter"])
    retrieval = read(RUN/"retrieval.json") if (RUN/"retrieval.json").exists() else None
    summary["retrieval"] = retrieval["metrics"] if retrieval else None
    if retrieval:
        modes = {mode: {r["question_id"]: r for r in retrieval["records"] if r["mode"] == mode}
                 for mode in ("vector", "hybrid")}
        assert set(modes["vector"]) == set(modes["hybrid"])
        summary["retrieval_paired_comparison"] = {key: {
            "gained_question_ids": [qid for qid, r in modes["vector"].items()
                if modes["hybrid"][qid][key] > r[key]],
            "lost_question_ids": [qid for qid, r in modes["vector"].items()
                if modes["hybrid"][qid][key] < r[key]]}
            for key in ("hit_at_5", "criterion_evidence_coverage_proxy")}
    attempts = ledger.report()
    for config in ("medical_base", "medical_adapter", "teaching_base", "teaching_adapter"):
        group = [r for r in attempts if r["config"] == config]
        process = RUN / (config + "-process.json")
        checkpoints = [read(path) for path in (RUN/config).glob("*.json")]
        timings = [r["generation_seconds"] for r in checkpoints if "generation_seconds" in r]
        archives = sorted((RUN/"segments"/config).glob("*/"+config+"-process.json"))
        process_data = read(process) if process.exists() else {"status": "not_run"}
        segments = [read(p) for p in archives]+[process_data]
        starts = [r["before"]["time_utc"] for r in segments if r.get("before", {}).get("time_utc")]
        after_path = RUN/(config+"-after-container-exit.json")
        wall_window = ((datetime.fromisoformat(read(after_path)["time_utc"])
                        - min(datetime.fromisoformat(t) for t in starts)).total_seconds()
                       if starts and after_path.exists() else None)
        summary["runtime"][config] = {"attempts": len(group),
            "generation_calls_started": sum(r["generation_started"] for r in group),
            "input_tokens_including_development": sum(r.get("input_tokens", 0) for r in checkpoints),
            "generated_tokens_including_development": sum(r.get("generated_tokens", 0) for r in checkpoints),
            "generation_seconds_sum": sum(timings),
            "generation_latency_median_seconds": percentile(timings, 50),
            "generation_latency_p95_seconds": percentile(timings, 95),
            "returned_raw_responses": len(list((RUN/config/"raw").glob("*.json"))),
            "archived_process_segments": [str(p.relative_to(RUN)) for p in archives],
            "archived_host_memory_files": [str(p.relative_to(RUN)) for p in
                sorted((RUN/"segments"/config).glob("*/"+config+"-host-memory.json"))],
            "observed_wall_window_including_recovery_idle_seconds": wall_window,
            "by_category": dict(Counter(r["category"] for r in group)),
            "process": process_data}
    summary["execution_attempts"] = len(attempts)
    summary["generation_calls_started"] = sum(r["generation_started"] for r in attempts)
    after = RUN/"after-experiment.json"
    before = RUN/"baseline.json"
    summary["model_experiment_wall_window_seconds"] = (
        (datetime.fromisoformat(read(after)["time_utc"])
         - datetime.fromisoformat(read(before)["host"]["time_utc"])).total_seconds()
        if after.exists() and before.exists() else None)
    summary["budget"] = read(DATA / "experiment.json")["budgets"]
    reviews = rows(RUN / "manual-review.jsonl") if (RUN / "manual-review.jsonl").exists() else []
    review_split = read(DATA/"split.json")
    no_history_ids = {r["sample_id"] for r in rows(DATA/"teaching-inputs.jsonl") if r["context_type"] == "none"}
    assert len(reviews) == len({(r["config"], r.get("stage", "raw"), r["sample_id"]) for r in reviews}), "Duplicate manual-review row"
    for item in reviews:
        assert item["config"] in summary["runtime"]
        ids = review_split["medical_review_sample_ids" if item["config"].startswith("medical") else "teaching_review_sample_ids"]
        assert item["sample_id"] in ids, "Qualitative discoveries outside the prespecified sample must stay separate"
    for config in summary["runtime"]:
        group = [r for r in reviews if r["config"] == config]
        fields = (read(RUN / "review-protocol.json")["medical_flags"] if config.startswith("medical") else ["role_violation", "context_used", "quality_level"])
        stages = ["raw"] if config.startswith("medical") else ["raw", "guarded"]
        summary["review"][config] = {"reviewer": "Codex agent, not a clinician", "stages": {}}
        for stage in stages:
            selected = [r for r in group if r.get("stage", "raw") == stage]
            planned_review = len(review_split["medical_review_sample_ids" if config.startswith("medical") else "teaching_review_sample_ids"])
            summary["review"][config]["stages"][stage] = {
                "n_reviewed": len(selected),
                "n_planned_for_review": planned_review,
                "n_pending_for_review": planned_review-len(selected),
                "n_with_semantic_assessment": sum(any(r.get(key) is not None for key in fields) for r in selected),
                "measures": {key: review_measure(selected, key, no_history_ids if key == "context_used" else None)
                             for key in fields},
                "quality_level_counts": dict(Counter(r["quality_level"] for r in selected if r.get("quality_level") is not None))}
    write(RUN / "metrics.json", summary)
    write(RUN / "execution-ledger.json", attempts)
    errors = []
    for config in summary["runtime"]:
        folder = RUN / config
        for path in sorted(folder.glob("*.json")):
            item = read(path)
            sid = item["sample_id"]
            if "parsed" in item:
                write(RUN / "parsed-raw" / config / (sid+".json"),
                      {"prediction": item["parsed"], "schema_valid": item["schema_valid"],
                       "contract_valid": item["contract_valid"], "source_checkpoint": str(path.relative_to(RUN))})
            if "guarded" in item:
                write(RUN / "guarded" / config / (sid+".json"),
                      {"prediction": item["guarded"], "proxy": item["guarded_proxy"],
                       "errors": item["guarded_errors"], "source_checkpoint": str(path.relative_to(RUN))})
            if item.get("error") or item.get("truncated"):
                errors.append({"config": config, "sample_id": sid, "attempt_id": item["attempt_id"],
                               "original_error": item.get("error"), "truncated": item.get("truncated", False)})
    write(RUN / "errors.json", errors)
    csv_write(RUN / "medical-per-sample.csv", all_medical)
    csv_write(RUN / "teaching-per-sample.csv", all_teaching)
    grouped = []
    for config in summary["medical"]:
        for dimension in ("topic", "answer_type"):
            for value in sorted({r[dimension] for r in all_medical if r["config"] == config}):
                records = [r for r in all_medical if r["config"] == config and r[dimension] == value]
                grouped.append({"config": config, "dimension": dimension, "group": value,
                                **summarize_medical(records)})
    csv_write(RUN / "medical-by-group.csv", grouped)
    csv_write(RUN / "medical-summary.csv", [{"config": c, **m} for c, m in summary["medical"].items()])
    csv_write(RUN / "teaching-summary.csv", [{"config": c, "stage": stage, **m}
        for c, stages in summary["teaching"].items() for stage, m in stages.items()])
    print(json.dumps({"attempts": len(attempts), "medical": summary["medical"],
                      "teaching": summary["teaching"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
