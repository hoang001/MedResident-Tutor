import json

import httpx
import pytest

from app.core.config import Settings
from app.modules.practice import providers
from app.modules.practice.contracts import (
    EvaluationRequest,
    ServiceError,
    validate_output,
    validate_teaching,
)
from app.modules.practice.service import teaching_payload

PAYLOAD = {
    "question": "Question",
    "student_answer": "Runtime answer",
    "rubric": {
        "rubric_id": "R",
        "question_id": "Q",
        "max_score": 1.0,
        "criteria": [
            {
                "criterion_id": "C",
                "description": "Defined criterion anchor",
                "max_score": 1.0,
                "required_source_unit_ids": ["SU"],
            }
        ],
    },
    "evidence": [
        {
            "source_unit_id": "SU",
            "source_id": "SRC",
            "title": "Evidence",
            "page_start": 16,
            "page_end": 16,
            "content": "Evidence content",
        }
    ],
}


async def test_mock_and_http_use_identical_contract(monkeypatch):
    mock = providers.MockProvider()
    medical, _ = await mock.evaluate("medical", PAYLOAD)
    validate_output(json.dumps(medical), EvaluationRequest.model_validate(PAYLOAD))
    teaching_input = teaching_payload(PAYLOAD, medical)
    teaching, _ = await mock.evaluate("teaching", teaching_input)
    assert validate_teaching(teaching_input, teaching) == teaching
    calls = []

    async def handler(request):
        calls.append(request)
        stage = "medical" if request.url.path == "/medical/evaluate" else "teaching"
        expected = PAYLOAD if stage == "medical" else teaching_input
        assert json.loads(request.content) == expected
        assert request.headers["X-API-Key"] == "test-key-only"
        return httpx.Response(
            200,
            json={
                stage + ("_evaluation" if stage == "medical" else "_feedback"): medical
                if stage == "medical"
                else teaching,
                "model_metadata": {"identity": "test-only"},
                "timing": {},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    provider = providers.HTTPProvider(
        Settings(
            medical_service_url="http://medical.invalid",
            teaching_service_url="http://teaching.invalid",
            medical_service_api_key="test-key-only",
            teaching_service_api_key="test-key-only",
        )
    )
    result, _ = await provider.evaluate("medical", PAYLOAD)
    assert validate_output(json.dumps(result), EvaluationRequest.model_validate(PAYLOAD)) == medical
    result, _ = await provider.evaluate("teaching", teaching_input)
    assert validate_teaching(teaching_input, result) == teaching
    assert len(calls) == 2


@pytest.mark.parametrize(
    "status,code",
    [(429, "PROVIDER_BUSY"), (500, "PROVIDER_FAILED"), (200, "PROVIDER_RESPONSE_INVALID")],
)
async def test_http_errors_never_fallback(monkeypatch, status, code):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, text="invalid")),
            **kw,
        ),
    )
    provider = providers.HTTPProvider(
        Settings(
            medical_service_url="http://medical.invalid",
            teaching_service_url="http://teaching.invalid",
            medical_service_api_key="test-only",
            teaching_service_api_key="test-only",
        )
    )
    with pytest.raises(ServiceError, match=code):
        await provider.evaluate("medical", PAYLOAD)


async def test_http_requires_both_explicit_configurations():
    with pytest.raises(ServiceError, match="HTTP_PROVIDER_NOT_CONFIGURED"):
        providers.HTTPProvider(Settings(medical_service_url="http://medical.invalid"))


def test_local_seed_identity_only_in_development(monkeypatch):
    from pydantic import ValidationError

    from app.modules.auth import schemas

    monkeypatch.setattr(
        schemas,
        "get_settings",
        lambda: Settings(app_env="development", seed_admin_email="seed@example.local"),
    )
    assert (
        schemas.LoginRequest(email="seed@example.local", password="test-only").email
        == "seed@example.local"
    )
    with pytest.raises(ValidationError):
        schemas.LoginRequest(email="other@example.local", password="test-only")
    monkeypatch.setattr(
        schemas,
        "get_settings",
        lambda: Settings(app_env="production", seed_admin_email="seed@example.local"),
    )
    with pytest.raises(ValidationError):
        schemas.LoginRequest(email="seed@example.local", password="test-only")
