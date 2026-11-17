import json

import httpx
import pytest

from app.ai.remote_chat import chat, chat_url, grading_messages
from app.core.config import Settings
from app.modules.practice.contracts import ServiceError
from app.modules.practice.providers import HTTPProvider, get_provider
from tests.test_practice_contracts import PAYLOAD


@pytest.mark.parametrize(
    "base,expected",
    [
        ("https://example.invalid", "https://example.invalid/v1/chat/completions"),
        ("https://example.invalid/v1/", "https://example.invalid/v1/chat/completions"),
        (
            "https://api.runpod.ai/v2/endpoint/openai/v1",
            "https://api.runpod.ai/v2/endpoint/openai/v1/chat/completions",
        ),
        (
            "https://example.invalid/v1/chat/completions",
            "https://example.invalid/v1/chat/completions",
        ),
    ],
)
def test_endpoint_join(base, expected):
    assert chat_url(base) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://<FILL>/v1",
        "https://user:secret@example.invalid",
        "https://example.invalid?key=secret",
    ],
)
def test_placeholder_or_credential_urls_rejected(url):
    with pytest.raises(ServiceError):
        chat_url(url)


async def test_remote_grading_uses_locked_prompts_and_full_evidence(monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        data = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fixture-only"
        assert data["temperature"] == 0 and data["stream"] is False
        assert json.loads(data["messages"][1]["content"])["evidence"] == PAYLOAD["evidence"]
        assert data["model"] == "medical-v1" and data["max_tokens"] == 1200
        return httpx.Response(
            200,
            json={
                "model": "medical-v1",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"fixture":true}'}}],
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    settings = Settings(
        practice_provider="http",
        model_calls_enabled=True,
        medical_api_format="openai",
        medical_service_url="https://medical.invalid/v1",
        medical_service_api_key="fixture-only",
        medical_model="medical-v1",
    )
    provider = HTTPProvider(settings, stages=("medical",))
    result, meta = await provider.evaluate("medical", PAYLOAD)
    assert result == {"fixture": True} and len(calls) == 1
    assert meta["model_metadata"]["api_format"] == "openai"
    from src.medical.inference import SYSTEM_PROMPT

    assert grading_messages("medical", PAYLOAD)[0]["content"] == SYSTEM_PROMPT
    from src.teaching.prepare_dataset import SYSTEM_PROMPT as TEACHING_PROMPT

    teaching = {
        k: {}
        for k in ("question", "student_answer", "medical_evaluation", "learner_context", "metadata")
    }
    assert grading_messages("teaching", teaching)[0]["content"] == TEACHING_PROMPT


@pytest.mark.parametrize("status", [401, 403, 500, 524])
async def test_remote_http_failure_is_single_attempt_and_redacted(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "secret echoed by upstream"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(ServiceError) as exc:
        await chat(
            base="https://example.invalid/v1",
            key="fixture",
            model="model",
            messages=[],
            max_tokens=1,
            timeout=10,
        )
    assert exc.value.status == status and exc.value.code == f"REMOTE_HTTP_{status}"
    assert len(calls) == 1 and "secret" not in str(exc.value)


def test_disabled_gate_and_missing_model():
    with pytest.raises(ServiceError, match="MODEL_CALLS_DISABLED"):
        get_provider(Settings(practice_provider="http", model_calls_enabled=False))
    with pytest.raises(ServiceError, match="HTTP_PROVIDER_NOT_CONFIGURED"):
        HTTPProvider(
            Settings(
                medical_api_format="openai",
                medical_service_url="https://example.invalid",
                medical_service_api_key="<FILL>",
                medical_model="",
            ),
            stages=("medical",),
        )


async def test_remote_authoring_is_separate_and_checks_references(monkeypatch):
    from fastapi import HTTPException

    from app.modules.questions import authoring

    settings = Settings(
        authoring_provider="openai",
        model_calls_enabled=True,
        authoring_service_url="https://author.invalid/v1",
        authoring_service_api_key="fixture",
        authoring_model="author-base",
    )
    monkeypatch.setattr(authoring, "get_settings", lambda: settings)
    scope = authoring.Scope(question="Independent question")
    evidence = [{"source_unit_id": "SOURCE", "content": "Full condition", "source_id": "BOOK"}]
    bundle = authoring.seal({"scope": scope.model_dump(), "evidence": evidence}, "evidence")
    value = {
        "reference_answer": "Source-backed draft",
        "criteria": [{"description": "Criterion", "max_score": 1, "source_unit_ids": ["SOURCE"]}],
        "insufficient_basis": [],
    }
    calls = []

    def handler(request):
        calls.append(request)
        data = json.loads(request.content)
        assert data["model"] == "author-base"
        assert json.loads(data["messages"][1]["content"])["evidence"] == evidence
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(value)}}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    body = authoring.ProposalRequest(scope=scope, bundle_token=bundle, selected_ids=["SOURCE"])
    result = await authoring.propose(body)
    assert authoring.unseal(result["proposal_token"], "proposal")["mode"] == "remote_openai"
    value["criteria"][0]["source_unit_ids"] = ["INVALID"]
    with pytest.raises(HTTPException):
        await authoring.propose(body)
    settings.model_calls_enabled = False
    with pytest.raises(Exception) as exc:
        await authoring.propose(body)
    assert getattr(exc.value, "code", None) == "MODEL_CALLS_DISABLED" and len(calls) == 2


async def test_both_remote_stages_keep_validated_contracts(monkeypatch):
    from app.modules.practice.contracts import EvaluationRequest, validate_output, validate_teaching
    from app.modules.practice.providers import MockProvider
    from app.modules.practice.service import teaching_payload

    medical, _ = await MockProvider().evaluate("medical", PAYLOAD)
    teaching_input = teaching_payload(PAYLOAD, medical)
    teaching, _ = await MockProvider().evaluate("teaching", teaching_input)
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        is_medical = body["model"] == "medical-v1"
        assert json.loads(body["messages"][1]["content"]) == (
            json.loads(grading_messages("medical", PAYLOAD)[1]["content"])
            if is_medical
            else json.loads(grading_messages("teaching", teaching_input)[1]["content"])
        )
        assert request.headers["Authorization"] == (
            "Bearer medical-fixture" if is_medical else "Bearer teaching-fixture"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(medical if is_medical else teaching)},
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    provider = HTTPProvider(
        Settings(
            medical_api_format="openai",
            teaching_api_format="openai",
            medical_service_url="https://medical.invalid/v1",
            teaching_service_url="https://teaching.invalid/v1",
            medical_service_api_key="medical-fixture",
            teaching_service_api_key="teaching-fixture",
            medical_model="medical-v1",
            teaching_model="teaching-v1",
        )
    )
    value, _ = await provider.evaluate("medical", PAYLOAD)
    assert validate_output(json.dumps(value), EvaluationRequest.model_validate(PAYLOAD)) == medical
    value, _ = await provider.evaluate("teaching", teaching_input)
    assert validate_teaching(teaching_input, value) == teaching and len(calls) == 2


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("length", "MODEL_OUTPUT_TRUNCATED"),
        ("invalid", "PROVIDER_RESPONSE_INVALID"),
        ("busy", "PROVIDER_BUSY"),
    ],
)
async def test_remote_bad_outputs_and_busy_never_retry(monkeypatch, kind, expected):
    calls = []

    def handler(request):
        calls.append(request)
        if kind == "busy":
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if kind == "length" else "stop",
                        "message": {"content": "not JSON"},
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(ServiceError, match=expected):
        await chat(
            base="https://example.invalid/v1",
            key="fixture",
            model="fixture",
            messages=[],
            max_tokens=1,
            timeout=10,
        )
    assert len(calls) == 1
