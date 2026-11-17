from local_model_testing.experiment.metrics import paired_bootstrap, percentile, review_measure, summarize_medical, summarize_teaching
from local_model_testing.experiment.retrieval import coverage, covered_length


def test_errors_remain_in_agreement_denominator_and_mae_has_coverage():
    good = {"attempted": True, "contract_valid": True, "schema_valid": True,
        "normalized_absolute_error": .5, "total_agreement": False, "vector_agreement": False,
        "wrong_criteria_valid": 1, "wrong_criteria_planned": 1, "wrong_criteria_awarded": 1,
        "sufficient_evidence_agreement": True, "generation_seconds": 2,
        "input_tokens": 100, "generated_tokens": 200, "truncated": False, "error_type": None}
    invalid = {**good, "contract_valid": False, "schema_valid": False,
        "normalized_absolute_error": None, "wrong_criteria_valid": 0, "wrong_criteria_awarded": 0,
        "error_type": "parse"}
    m = summarize_medical([good, invalid])
    assert m["exact_total_score_agreement"] == 0
    assert m["mae_normalized"] == .5 and m["mae_coverage"] == .5
    assert m["wrong_criterion_award_rate"] == 1 and m["wrong_criterion_coverage"] == .5
    assert m["failed_attempts"] == 1 and m["error_types"] == {"parse": 1}


def test_overlap_does_not_inflate_retrieval_coverage():
    assert covered_length([(0, 8), (4, 10), (0, 8)]) == 10
    p = {"source_id": "S", "pdf_page": 3, "source_window_start": 0, "source_window_end": 20}
    chunk = {"source_id": "S", "page": 3, "start": 0, "end": 10}
    result = coverage([chunk, chunk], p)
    assert result["hit_at_5"] and result["strict_source_span_coverage"] == .5
    # Two small fragments can provide joint coverage but no single relevant Hit@5.
    pieces = [{**chunk, "start": 0, "end": 5}, {**chunk, "start": 15, "end": 20}]
    result = coverage(pieces, p)
    assert not result["hit_at_5"] and result["strict_source_span_coverage"] == .5


def test_latency_percentiles_and_empty_metrics_are_explicit():
    assert percentile([], 95) is None
    assert percentile([10, 20, 30], 50) == 20
    assert summarize_medical([])["mae_normalized"] is None


def test_teaching_context_denominator_and_stages_do_not_double_token_cost():
    records = []
    for stage in ("raw", "guarded"):
        for context in ("none", "recurring", "improving"):
            records.append({"stage": stage, "context_type": context, "attempted": True,
                "schema_valid": True, "alignment_proxy_pass": True,
                "context_proxy_pass": None if context == "none" else context == "recurring",
                "forbidden_score_keys_proxy_pass": True, "anchor_proxy_pass": True,
                "truncated": False, "error_type_derived": None, "generation_seconds": 2,
                "input_tokens": 100, "generated_tokens": 50})
    result = summarize_teaching(records)
    for stage in ("raw", "guarded"):
        assert result[stage]["context_denominator"] == 2
        assert result[stage]["context_usage_proxy_pass_rate"] == .5
        assert result[stage]["planned"] == 3
        assert result[stage]["input_tokens"] == 300


def test_paired_cluster_ci_is_zero_for_identical_outputs():
    records = [{"sample_id": str(i), "topic": str(i//5),
                "total_agreement": bool(i%2), "vector_agreement": bool(i%2)} for i in range(10)]
    result = paired_bootstrap(records, records)
    assert result["clusters"] == 2
    for value in result["metrics"].values():
        assert value["adapter_minus_base"] == 0
        assert value["cluster_bootstrap_95_ci"] == [0, 0]


def test_no_history_is_not_an_unknown_context_review():
    records = [{"sample_id": "none", "context_used": None},
               {"sample_id": "recurring", "context_used": False},
               {"sample_id": "ambiguous", "context_used": None}]
    assert review_measure(records, "context_used", {"none"}) == {
        "n_known": 1, "n_unknown": 1, "n_not_applicable": 1, "mean_or_rate": 0}
