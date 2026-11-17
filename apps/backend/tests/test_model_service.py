"""Unified-service boundaries: synthetic fixtures, no network or model loading."""

import copy
import json

import httpx
import pytest

from app.ai.model_service import ModelServiceClient, ModelServiceError
from app.core.config import Settings
from app.modules.practice.contracts import ServiceError
from app.modules.practice.providers import MockProvider, RunPodProvider, get_provider
from app.modules.practice.service import teaching_payload
from tests.test_practice_contracts import PAYLOAD


def config(**overrides):
    return Settings(
        _env_file=None,
        model_service_base_url="https://fixture.invalid/",
        model_service_api_key="synthetic-only-api-key",
        practice_provider="runpod",
        model_calls_enabled=True,
        **overrides,
    )


async def outputs():
    mock = MockProvider()
    medical, _ = await mock.evaluate("medical", PAYLOAD)
    payload = teaching_payload(PAYLOAD, medical)
    feedback, _ = await mock.evaluate("teaching", payload)
    return medical, payload, feedback


async def test_both_requests_status_and_independent_anchors():
    medical, teaching, feedback = await outputs()
    original = copy.deepcopy(teaching)
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.headers["X-API-Key"] == "synthetic-only-api-key"
        assert "authorization" not in request.headers
        if request.url.path in {"/health", "/ready"}:
            return httpx.Response(
                200, json={"status": "healthy" if request.url.path == "/health" else "ready"}
            )
        assert request.headers["content-type"] == "application/json"
        assert request.headers["X-Request-ID"] == "synthetic-request"
        payload = json.loads(request.content)
        if request.url.path == "/medical/evaluate":
            assert payload == PAYLOAD
            return httpx.Response(
                200,
                json={
                    "medical_evaluation": medical,
                    "model_metadata": {"model_id": "medical-v1"},
                    "timing": {"input_tokens": 5},
                },
            )
        assert request.url.path == "/teaching/feedback" and payload == teaching
        assert "evidence" not in payload and "rubric" not in payload
        return httpx.Response(
            200, json={"teaching_feedback": feedback, "model_metadata": {"model_id": "teaching-v1"}}
        )

    client = ModelServiceClient(config(), transport=httpx.MockTransport(handler))
    assert await client.health() == {"status": "healthy"}
    assert await client.ready() == {"status": "ready"}
    assert (await client.medical_evaluate(PAYLOAD, request_id="synthetic-request")).value == medical
    assert (
        await client.teaching_feedback(teaching, request_id="synthetic-request")
    ).value == feedback
    assert teaching == original and len(calls) == 4
    assert "total_score" not in feedback


@pytest.mark.parametrize(
    "status,code,upstream",
    [
        (401, "MODEL_SERVICE_UNAUTHORIZED", "UNAUTHORIZED"),
        (403, "MODEL_SERVICE_UNAUTHORIZED", None),
        (429, "MODEL_SERVICE_BUSY", "INFERENCE_BUSY"),
        (503, "MODEL_SERVICE_NOT_READY", "TEACHING_MODEL_LOADING"),
        (413, "MODEL_INPUT_TOO_LARGE", "REQUEST_TOO_LARGE"),
        (502, "MODEL_INFERENCE_FAILED", "MODEL_OUTPUT_INVALID_JSON"),
        (500, "MODEL_INFERENCE_FAILED", None),
        (524, "MODEL_SERVICE_TIMEOUT", None),
        (404, "MODEL_INFERENCE_FAILED", None),
        (422, "MODEL_INPUT_INVALID", "INVALID_REQUEST"),
    ],
)
async def test_status_mapping_no_retry_or_secret_echo(status, code, upstream):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"code": upstream, "message": "synthetic-only-api-key"}}
        )

    client = ModelServiceClient(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelServiceError) as caught:
        await client.medical_evaluate(PAYLOAD)
    assert caught.value.code == code and caught.value.upstream_status == status
    assert caught.value.upstream_code == upstream and len(calls) == 1
    assert "synthetic-only-api-key" not in str(caught.value)


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ConnectTimeout, "MODEL_SERVICE_UNAVAILABLE"),
        (httpx.ReadTimeout, "MODEL_SERVICE_TIMEOUT"),
        (httpx.ConnectError, "MODEL_SERVICE_UNAVAILABLE"),
        (httpx.WriteTimeout, "MODEL_SERVICE_TIMEOUT"),
    ],
)
async def test_transport_mapping_and_timeouts(exception, code):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.extensions["timeout"]["connect"] == 10
        assert request.extensions["timeout"]["read"] == 120
        raise exception("do not echo synthetic-only-api-key", request=request)

    client = ModelServiceClient(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelServiceError, match=code):
        await client.medical_evaluate(PAYLOAD)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"medical_evaluation":NaN}',
        '{"medical_evaluation":{},"medical_evaluation":{}}',
        '{"medical_evaluation":{}}',
    ],
)
async def test_invalid_response_is_not_mocked(raw):
    client = ModelServiceClient(
        config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, text=raw))
    )
    with pytest.raises(ModelServiceError, match="MODEL_INFERENCE_FAILED"):
        await client.medical_evaluate(PAYLOAD)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("TEACHING_ALIGNMENT_INVALID", "TEACHING_ALIGNMENT_INVALID"),
        ("private upstream message", None),
        ("synthetic-only-api-key", None),
    ],
)
async def test_safe_error_header_used_when_upstream_body_is_not_json(header, expected):
    client = ModelServiceClient(
        config(), transport=httpx.MockTransport(lambda _: httpx.Response(
            502, text="<html>Bad gateway</html>",
            headers={"X-Model-Error-Code": header},
        )),
    )
    _, payload, _ = await outputs()
    with pytest.raises(ModelServiceError) as caught:
        await client.teaching_feedback(payload)
    assert caught.value.upstream_status == 502
    assert caught.value.upstream_code == expected


async def test_teaching_cannot_return_scores_or_regrade():
    medical, payload, feedback = await outputs()
    invalid = {**feedback, "total_score": 9}
    client = ModelServiceClient(
        config(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"teaching_feedback": invalid})
        ),
    )
    with pytest.raises(ModelServiceError, match="MODEL_INFERENCE_FAILED"):
        await client.teaching_feedback(payload)
    assert payload["medical_evaluation"] == medical


def test_provider_explicit_gates_and_stage_deadlines():
    settings = config()
    assert isinstance(get_provider(settings), RunPodProvider)
    assert get_provider(settings).mode == "http"
    assert settings.practice_stage_deadline("medical") == 150
    assert settings.practice_request_timeout_ms() == 310000
    with pytest.raises(ServiceError, match="MODEL_CALLS_DISABLED"):
        get_provider(settings.model_copy(update={"model_calls_enabled": False}))
    with pytest.raises(ModelServiceError, match="MODEL_SERVICE_NOT_CONFIGURED"):
        get_provider(
            settings.model_copy(
                update={
                    "model_service_api_key": "<FILL>",
                    "medical_service_api_key": "old-key-not-used",
                }
            )
        )
    for base in [
        "https://user:secret@fixture.invalid",
        "https://fixture.invalid/v1",
        "https://fixture.invalid?key=x",
    ]:
        with pytest.raises(ModelServiceError, match="MODEL_SERVICE_URL_INVALID"):
            ModelServiceClient(settings.model_copy(update={"model_service_base_url": base}))


async def test_pod_env_changes_route_requests_and_explicit_url_still_overrides(
    tmp_path, monkeypatch
):
    env = tmp_path / ".env"
    env.write_text(
        "RUNPOD_POD_ID=firstpod\nMODEL_SERVICE_BASE_URL=\n"
        "MODEL_SERVICE_API_KEY=synthetic-test-key-only\n",
        encoding="utf-8",
    )
    for name in ("RUNPOD_POD_ID", "MODEL_SERVICE_BASE_URL", "MODEL_SERVICE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    requests = []

    def respond(request):
        requests.append(str(request.url))
        assert request.headers["X-API-Key"] == "synthetic-test-key-only"
        return httpx.Response(200, json={"status": "ready"})

    async def probe():
        settings = Settings(_env_file=env)
        return await ModelServiceClient(settings, transport=httpx.MockTransport(respond)).ready()

    assert await probe() == {"status": "ready"}
    monkeypatch.setenv("RUNPOD_POD_ID", "secondpod")
    await probe()
    monkeypatch.setenv("MODEL_SERVICE_BASE_URL", "http://localhost:8000/")
    await probe()
    assert requests == [
        "https://firstpod-8000.proxy.runpod.net/ready",
        "https://secondpod-8000.proxy.runpod.net/ready",
        "http://localhost:8000/ready",
    ]


@pytest.mark.parametrize(
    "pod_id", ["<ID>", "https://pod.example", "pod/path", "a.b", "a\nkey", "a" * 59]
)
def test_pod_id_cannot_inject_a_different_origin_or_path(pod_id):
    settings = config().model_copy(update={"model_service_base_url": "", "runpod_pod_id": pod_id})
    with pytest.raises(ModelServiceError, match="MODEL_SERVICE_POD_ID_INVALID"):
        ModelServiceClient(settings)
