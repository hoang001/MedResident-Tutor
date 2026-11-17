import asyncio

import pytest

from app.core.config import Settings
from app.modules.practice.contracts import ServiceError
from app.modules.practice.providers import HTTPProvider
from local_model_testing.retrieval_confirmation import backend


def test_live_router_and_http_share_local_medical_deadline():
    base = Settings(
        _env_file=None, app_env="development", practice_runtime_profile="default"
    )
    settings = backend.practice_settings(base, live=True)
    provider = HTTPProvider(
        settings.model_copy(
            update={
                "medical_service_url": "http://medical.test",
                "medical_service_api_key": "test-fixture",
            }
        ),
        stages=("medical",),
    )
    assert settings.practice_transport_timeouts("medical")["read"] == 600
    assert settings.practice_stage_deadline("medical") == 625
    assert provider.settings.practice_stage_deadline("medical") == 625
    assert (
        backend.practice_settings(base, live=False).practice_stage_deadline("medical")
        == 30
    )
    assert base.practice_runtime_profile == "default"


@pytest.mark.asyncio
async def test_cancelled_http_is_terminal_and_not_retried(monkeypatch):
    recorded = []
    monkeypatch.setattr(backend.ledger, "finish", lambda *args: recorded.append(args))
    calls = 0

    async def invoke():
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await backend.recorded_medical_call(1, invoke)
    assert calls == 1
    assert recorded == [
        (
            1,
            "failed",
            {
                "code": "PROVIDER_CANCELLED",
                "server_generation_may_finish": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_busy_response_keeps_http_status_without_retry(monkeypatch):
    recorded = []
    monkeypatch.setattr(backend.ledger, "finish", lambda *args: recorded.append(args))
    calls = 0

    async def invoke():
        nonlocal calls
        calls += 1
        raise ServiceError("PROVIDER_BUSY", 429)

    with pytest.raises(ServiceError) as exc:
        await backend.recorded_medical_call(2, invoke)
    assert exc.value.status == 429 and calls == 1
    assert recorded == [(2, "failed", {"code": "PROVIDER_BUSY", "http_status": 429})]
