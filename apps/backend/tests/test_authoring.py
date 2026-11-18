import copy

import pytest
from fastapi import HTTPException

from app.ai.retrieval.evidence import digest
from app.modules.questions.authoring import (
    ProposalRequest,
    Scope,
    Selection,
    approved_payload,
    propose,
    seal,
    selected,
    validate_proposal,
)

EVIDENCE = [
    {
        "source_unit_id": "new_source",
        "source_id": "book",
        "content": "source conditions",
        "page_start": 1,
        "page_end": 1,
        "title": "Chapter",
    }
]


def test_evidence_cannot_be_injected_or_forged():
    token = seal({"evidence": EVIDENCE}, "evidence")
    assert selected(Selection(bundle_token=token, selected_ids=["new_source"]))[1] == EVIDENCE
    with pytest.raises(HTTPException):
        selected(Selection(bundle_token=token, selected_ids=["invented"]))
    with pytest.raises(HTTPException):
        selected(Selection(bundle_token=token + "x", selected_ids=["new_source"]))


def test_proposal_rejects_foreign_sources_and_wrong_points():
    value = {
        "reference_answer": "Conditions",
        "criteria": [
            {"description": "Conditions", "max_score": 1, "source_unit_ids": ["new_source"]}
        ],
        "insufficient_basis": [],
    }
    assert validate_proposal(value, EVIDENCE, 1) == value
    with pytest.raises(HTTPException):
        validate_proposal(value, EVIDENCE, 2)
    value["criteria"][0]["source_unit_ids"] = ["foreign"]
    with pytest.raises(HTTPException):
        validate_proposal(value, EVIDENCE, 1)
    from pydantic import ValidationError

    value["criteria"][0]["source_unit_ids"] = ["new_source", "new_source"]
    with pytest.raises(ValidationError):
        validate_proposal(value, EVIDENCE, 1)


async def test_changed_question_does_not_call_model():
    scope = Scope(question="Unseen question without benchmark ID")
    token = seal({"scope": scope.model_dump(), "evidence": EVIDENCE}, "evidence")
    scope.question = "different question"
    with pytest.raises(HTTPException) as exc:
        await propose(ProposalRequest(scope=scope, bundle_token=token, selected_ids=["new_source"]))
    assert exc.value.status_code == 409


def test_package_is_hashed_and_answer_is_per_attempt():
    from types import SimpleNamespace

    value = {
        "payload": {"question": "Q", "evidence": EVIDENCE, "student_answer": "assembly"},
        "revision_id": "R1",
    }
    value["sha256"] = digest(value)
    original = copy.deepcopy(value)
    q = SimpleNamespace(import_metadata={"approved_package": value})
    payload, _ = approved_payload(q, "answer A")
    assert payload["evidence"] == EVIDENCE and payload["student_answer"] == "answer A"
    assert value == original
    value["payload"]["evidence"][0]["content"] = "tampered"
    with pytest.raises(HTTPException):
        approved_payload(q, "answer B")


async def test_no_evidence_never_calls_model():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProposalRequest(scope=Scope(question="Q"), bundle_token="not-used", selected_ids=[])


def test_ai_proposal_requires_explicit_admin_review_before_save():
    from pydantic import ValidationError

    from app.modules.questions.schemas import QuestionEdit

    body = {
        "content": "Q",
        "rubric_name": "R",
        "max_score": 1.0,
        "proposal_token": "synthetic-token",
        "criteria": [],
    }
    with pytest.raises(ValidationError, match="Review"):
        QuestionEdit.model_validate(body)
    assert QuestionEdit.model_validate({**body, "proposal_reviewed": True}).proposal_reviewed


async def test_runpod_authoring_uses_shared_client_and_seals_original_scope(monkeypatch):
    import app.modules.questions.authoring as module
    from app.ai.model_service import ModelServiceClient

    settings = module.get_settings().model_copy(
        update={
            "authoring_provider": "runpod",
            "model_calls_enabled": True,
            "model_service_base_url": "https://fixture.invalid",
            "model_service_api_key": "synthetic-test-api-key",
        }
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    value = {
        "reference_answer": "Condition A",
        "criteria": [
            {"description": "Condition A", "max_score": 1, "source_unit_ids": ["new_source"]}
        ],
        "insufficient_basis": [],
    }
    calls = []

    async def respond(self, payload):
        calls.append(payload)
        wire_value = copy.deepcopy(value)
        wire_value["criteria"][0]["source_unit_ids"] = [payload["evidence"][0]["source_unit_id"]]
        return {"proposal": wire_value, "model_metadata": {"adapter_enabled": False}, "timing": {}}

    monkeypatch.setattr(ModelServiceClient, "authoring_propose", respond)
    scope = Scope(question="Question with source")
    token = seal({"scope": scope.model_dump(), "evidence": EVIDENCE}, "evidence")
    result = await propose(
        ProposalRequest(scope=scope, bundle_token=token, selected_ids=["new_source"])
    )
    assert result["reference_answer"] == "Condition A" and len(calls) == 1
    provenance = module.unseal(result["proposal_token"], "proposal")
    assert provenance["scope"] == scope.model_dump()
    assert provenance["mode"] == "runpod_base_model"
    assert calls[0]["evidence"] == [{**EVIDENCE[0], "source_unit_id": "E1"}]
    assert result["criteria"][0]["source_unit_ids"] == ["new_source"]


async def test_http_replay_authoring_contract(monkeypatch):
    import httpx

    import app.modules.questions.authoring as module

    settings = module.get_settings().model_copy(
        update={
            "authoring_provider": "local_http",
            "authoring_service_url": "http://localhost:8103",
        }
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    scope = Scope(question="An entirely new non-benchmark question")
    evidence = copy.deepcopy(EVIDENCE)
    token = seal({"scope": scope.model_dump(), "evidence": evidence}, "evidence")
    value = {
        "reference_answer": "Replay fixture only",
        "criteria": [
            {"description": "Criterion", "max_score": 1, "source_unit_ids": ["new_source"]}
        ],
        "insufficient_basis": [],
    }

    def handler(request):
        import json

        payload = json.loads(request.content)
        assert payload["evidence"] == evidence
        assert payload["version"] == "authoring-v1"
        return httpx.Response(200, json=value)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await propose(
        ProposalRequest(scope=scope, bundle_token=token, selected_ids=["new_source"])
    )
    assert result["reference_answer"] == "Replay fixture only"
    assert module.unseal(result["proposal_token"], "proposal")["proposal"] == value


@pytest.mark.parametrize("generated_id", ["E01", "new_source"])
async def test_runpod_does_not_guess_or_repair_unknown_source_aliases(monkeypatch, generated_id):
    import app.modules.questions.authoring as module
    from app.ai.model_service import ModelServiceClient

    settings = module.get_settings().model_copy(
        update={
            "authoring_provider": "runpod",
            "model_calls_enabled": True,
            "model_service_base_url": "https://fixture.invalid",
            "model_service_api_key": "synthetic-test-api-key",
        }
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    calls = []

    async def respond(self, payload):
        calls.append(payload)
        return {
            "proposal": {
                "reference_answer": "Condition A",
                "criteria": [
                    {"description": "A", "max_score": 1, "source_unit_ids": [generated_id]}
                ],
                "insufficient_basis": [],
            }
        }

    monkeypatch.setattr(ModelServiceClient, "authoring_propose", respond)
    scope = Scope(question="Question with source")
    token = seal({"scope": scope.model_dump(), "evidence": EVIDENCE}, "evidence")
    with pytest.raises(HTTPException, match="unknown evidence"):
        await propose(ProposalRequest(scope=scope, bundle_token=token, selected_ids=["new_source"]))
    assert len(calls) == 1


async def test_runpod_restores_multiple_exact_source_ids_and_provenance(monkeypatch):
    import app.modules.questions.authoring as module
    from app.ai.model_service import ModelServiceClient

    settings = module.get_settings().model_copy(
        update={
            "authoring_provider": "runpod",
            "model_calls_enabled": True,
            "model_service_base_url": "https://fixture.invalid",
            "model_service_api_key": "synthetic-test-api-key",
        }
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    evidence = [*EVIDENCE, {**EVIDENCE[0], "source_unit_id": "RB1_another_exact_id"}]

    async def respond(self, payload):
        assert [e["source_unit_id"] for e in payload["evidence"]] == ["E1", "E2"]
        assert [e["content"] for e in payload["evidence"]] == [e["content"] for e in evidence]
        return {
            "proposal": {
                "reference_answer": "Condition A",
                "criteria": [{"description": "A", "max_score": 1, "source_unit_ids": ["E2", "E1"]}],
                "insufficient_basis": [],
            }
        }

    monkeypatch.setattr(ModelServiceClient, "authoring_propose", respond)
    scope = Scope(question="Question with two sources")
    selected_ids = [e["source_unit_id"] for e in reversed(evidence)]
    token = seal({"scope": scope.model_dump(), "evidence": evidence}, "evidence")
    result = await propose(
        ProposalRequest(scope=scope, bundle_token=token, selected_ids=selected_ids)
    )
    assert result["criteria"][0]["source_unit_ids"] == ["RB1_another_exact_id", "new_source"]
    provenance = module.unseal(result["proposal_token"], "proposal")
    assert provenance["proposal"]["criteria"] == result["criteria"]
    assert provenance["selected_ids"] == selected_ids
