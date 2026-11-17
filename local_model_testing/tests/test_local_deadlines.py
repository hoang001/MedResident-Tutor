"""Timeout/config tests with controlled providers; no LLM or database mutation."""

import asyncio
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from local_model_testing.common import ROOT, REPORT_BASE, read

sys.path.insert(0, str(ROOT / "apps/backend"))
from app.core.config import Settings
from app.modules.practice import providers, service
from app.modules.practice.contracts import ServiceError


def settings(**updates):
    return Settings(
        _env_file=None,
        app_env="development",
        practice_runtime_profile="local",
        **updates,
    )


def test_local_profile_budgets_and_legacy_defaults():
    local = settings()
    assert local.practice_transport_timeouts("medical") == dict(
        connect=5, read=90, write=10, pool=5
    )
    assert local.practice_stage_deadline("medical") == 115
    assert local.practice_stage_deadline("teaching") == 30
    assert local.practice_request_timeout_ms() == 155000
    for environment in ("production", "development"):
        default = Settings(
            _env_file=None, app_env=environment, practice_runtime_profile="default"
        )
        assert (
            default.practice_timeout_seconds
            == Settings.model_fields["practice_timeout_seconds"].default
            == 30
        )
        assert default.practice_transport_timeouts("medical") == dict(
            connect=30, read=30, write=30, pool=30
        )
        assert (
            default.practice_stage_deadline("medical")
            == default.practice_stage_deadline("teaching")
            == 30
        )


def test_profile_rejects_invalid_values_or_production_activation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", practice_runtime_profile="local")
    with pytest.raises(ValidationError):
        settings(practice_local_connect_seconds=0)
    with pytest.raises(ValidationError):
        settings(practice_local_medical_read_seconds=float("inf"))


def test_config_exposes_long_browser_budget_only_for_explicit_local_http(monkeypatch):
    from app.modules.practice import router

    monkeypatch.setattr(router, "get_settings", lambda: settings())
    monkeypatch.setattr(router, "provider", lambda: SimpleNamespace(mode="http"))
    assert asyncio.run(router.config(None)) == {
        "execution_mode": "http",
        "request_timeout_ms": 155000,
    }
    monkeypatch.setattr(router, "provider", lambda: SimpleNamespace(mode="mock"))
    assert asyncio.run(router.config(None)) == {"execution_mode": "mock"}
    monkeypatch.setattr(
        router,
        "get_settings",
        lambda: Settings(_env_file=None, practice_runtime_profile="default"),
    )
    monkeypatch.setattr(router, "provider", lambda: SimpleNamespace(mode="http"))
    assert asyncio.run(router.config(None)) == {"execution_mode": "http"}


def test_real_http_provider_local_transport_and_no_implicit_teaching(monkeypatch):
    requests = []

    async def response(request):
        requests.append(request)
        return httpx.Response(200, json={"medical_evaluation": {"fixture": True}})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(response), **kwargs),
    )
    provider = providers.HTTPProvider(
        settings(
            medical_service_url="http://local.test",
            medical_service_api_key="unit-test-only",
        ),
        stages=("medical",),
    )
    value, _ = asyncio.run(provider.evaluate("medical", {}))
    assert value == {"fixture": True}
    assert len(requests) == 1 and requests[0].extensions["timeout"] == dict(
        connect=5, read=90, write=10, pool=5
    )
    with pytest.raises(ServiceError, match="HTTP_STAGE_NOT_CONFIGURED"):
        asyncio.run(provider.evaluate("teaching", {}))
    assert len(requests) == 1


def test_http_read_timeout_maps_once_without_fallback(monkeypatch):
    calls = []

    async def response(request):
        calls.append(request)
        raise httpx.ReadTimeout("simulated read timeout")

    client = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(response), **kwargs),
    )
    provider = providers.HTTPProvider(
        settings(
            medical_service_url="http://local.test",
            medical_service_api_key="unit-test-only",
        ),
        stages=("medical",),
    )
    with pytest.raises(ServiceError) as exc:
        asyncio.run(provider.evaluate("medical", {}))
    assert (
        exc.value.code == "PROVIDER_TIMEOUT"
        and exc.value.status == 504
        and len(calls) == 1
    )


def test_local_experiment_cannot_start_batch_or_teaching(tmp_path, monkeypatch):
    from local_model_testing import launch

    (tmp_path / "local-profile.json").write_text("{}")
    monkeypatch.setattr(launch, "REPORT", tmp_path)
    for kind in ("medical", "teaching"):
        with pytest.raises(RuntimeError, match="LOCAL_PROFILE_MEDICAL_HTTP_ONLY"):
            launch.start(kind, False)


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @asynccontextmanager
    async def begin(self):
        yield self


def run_process(monkeypatch, *, delay, deadline, ignore_cancel=False):
    payload = read(REPORT_BASE / "inputs/CLINICAL_DEMO_V1_CASE01__full.json")
    row = SimpleNamespace(
        execution_mode="http",
        status="pending",
        lease_until=None,
        claim_token=None,
        medical_evaluation=None,
        teaching_feedback=None,
        snapshot={"payload": payload},
        provider_metadata={},
        stage_error=None,
    )

    async def owned(*args, **kwargs):
        return row

    monkeypatch.setattr(service, "owned", owned)

    class Provider:
        mode = "http"

        def __init__(self):
            self.fixture = providers.MockProvider()

        async def evaluate(self, stage, payload, retry=False):
            if stage == "medical":
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    if not ignore_cancel:
                        raise
                    await asyncio.sleep(0.005)
            return await self.fixture.evaluate(stage, payload)

    provider = Provider()
    asyncio.run(service.process(Session, "user", "attempt", provider, deadline))
    return row, provider


def test_response_after_old_deadline_within_local_deadline_is_accepted(monkeypatch):
    profile = settings(
        practice_timeout_seconds=0.01,
        practice_local_medical_read_seconds=0.08,
        practice_local_connect_seconds=0.005,
        practice_local_write_seconds=0.005,
        practice_local_pool_seconds=0.005,
        practice_local_deadline_grace_seconds=0.005,
    )
    row, p = run_process(
        monkeypatch, delay=0.04, deadline=profile.practice_stage_deadline
    )
    assert (
        row.status == "completed" and row.medical_evaluation and row.teaching_feedback
    )
    assert p.fixture.calls == {"medical": 1, "teaching": 1}


@pytest.mark.parametrize("ignore_cancel", [False, True])
def test_timeout_discards_late_output_and_does_not_retry(monkeypatch, ignore_cancel):
    row, p = run_process(
        monkeypatch, delay=0.05, deadline=0.01, ignore_cancel=ignore_cancel
    )
    assert row.status == "medical_failed" and row.stage_error == {
        "stage": "medical",
        "code": "PROVIDER_TIMEOUT",
    }
    assert (
        row.medical_evaluation is None
        and row.claim_token is None
        and row.teaching_feedback is None
    )
    before = dict(p.fixture.calls)
    asyncio.run(service.process(Session, "user", "attempt", p, 0.01))
    assert p.fixture.calls == before
