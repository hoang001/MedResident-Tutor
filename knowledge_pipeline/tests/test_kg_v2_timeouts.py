"""Connection-only mode must survive long generations and still bound connections."""

from types import SimpleNamespace

import httpx
import pytest

from document_toolkit.common import read_json, write_json
from document_toolkit.llm_client import LLMError
from knowledge_pipeline.kg_v2 import draft_run, pipeline, transport
from knowledge_pipeline.kg_v2.batch import run_batch
from knowledge_pipeline.tests.test_kg_v2_draft import (
    prepared,
    settings,
    successful_response,
)


def test_long_responses_complete_across_shards_without_total_deadline(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "prepare", prepared)
    monkeypatch.setattr(draft_run.Settings, "from_env", settings)
    clock = [0.0]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    calls = []

    def respond(request):
        assert request.extensions["timeout"] == {
            "connect": 17,
            "read": None,
            "write": None,
            "pool": None,
        }
        calls.append(request)
        clock[0] += 720  # Longer than the old per-request and per-shard budgets.
        return successful_response(request)

    monkeypatch.setattr(
        pipeline.httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond)
    )
    write_json(tmp_path / "s1.json", {"ids": ["a", "b"]})
    write_json(tmp_path / "s2.json", {"ids": ["c"]})
    plan = tmp_path / "plan.json"
    write_json(
        plan,
        {
            "shards": [
                {"key": "one", "scope": "s1.json"},
                {"key": "two", "scope": "s2.json"},
            ]
        },
    )
    output = tmp_path / "data/knowledge-extraction/v2/unlimited"
    options = {
        "max_calls": 3,
        "total_seconds": 1,
        "no_response_timeout": True,
        "connect_timeout_seconds": 17,
        "draft_registry_path": tmp_path / "ids.json",
    }
    result = run_batch(plan, output, **options)
    assert len(calls) == 3 and result["shards_started"] == 2
    assert result["budget"]["wait_seconds"] == 2160
    assert result["budget"]["total_seconds"] is None
    state = read_json(output / "batch-state.json")
    assert state["latest_result"]["windows_with_raw_output"] == 3
    generation = read_json(output / "shards/one/audit/manifest.json")["generation"]
    assert generation["timeout"] is None
    assert generation["connect_timeout_seconds"] == 17
    run_batch(plan, output, resume=True, **options)
    assert len(calls) == 3  # Compatible resume still uses cached responses.


def test_connection_timeout_is_reported_and_request_cap_still_applies():
    def respond(request):
        assert request.extensions["timeout"]["connect"] == 2
        raise httpx.ConnectTimeout("private-fixture", request=request)

    budget = transport.RequestBudget(1, None)
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        llm = transport.BudgetedLLM(
            settings(),
            http,
            budget,
            lambda rows: None,
            no_response_timeout=True,
            connect_timeout_seconds=2,
        )
        with pytest.raises(LLMError) as caught:
            llm.chat_json("fake", [{"role": "user", "content": "test"}])
        assert caught.value.diagnostics["error_type"] == "ConnectTimeout"
        assert caught.value.diagnostics["timeout_seconds"] is None
        assert caught.value.diagnostics["connect_timeout_seconds"] == 2
        with pytest.raises(transport.BudgetExhausted):
            llm.chat_json("fake", [{"role": "user", "content": "test"}])
    assert budget.calls == 1
