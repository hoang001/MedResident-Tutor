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
