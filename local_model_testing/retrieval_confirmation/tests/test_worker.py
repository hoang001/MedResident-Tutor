import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.modules.practice.providers import MockProvider
from medical_service.app import create_app
from medical_service.config import Settings
from local_model_testing.retrieval_confirmation.common import RUN, read
from local_model_testing.retrieval_confirmation.state import (
    attach_worker_state,
    can_continue,
)


@pytest.mark.asyncio
async def test_readiness_is_not_idle_and_cancellation_keeps_actual_service_lock():
    payload = read(RUN / "planned-medical-payloads.json")[0]["payload"]
    prediction, _ = await MockProvider().evaluate("medical", payload)
    entered, release = threading.Event(), threading.Event()
    state = {
        "status": "ready",
        "generation_attempt_ids": [],
        "generation_finished_ids": [],
    }
    key = "cpu-only-state-fixture-key"

    class FakeRunner:
        metadata = {"execution": "CPU fake runner; no model generation"}

        def load(self):
            pass

        def close(self):
            pass

        def generate(self, _):
            state["generation_attempt_ids"].append(1)
            state["active_runner_trace_id"] = "cpu-test"
            entered.set()
            try:
                assert release.wait(5)
                return SimpleNamespace(
                    text=json.dumps(prediction),
                    inference_seconds=0,
                    input_tokens=0,
                    generated_tokens=0,
                )
            finally:
                state["active_runner_trace_id"] = None
                state["generation_finished_ids"].append(1)

    settings = Settings(
        Path("/tmp/base"), Path("/tmp/adapter"), "0" * 64, "0" * 64, key, "0" * 64
    )
    app = create_app(settings, FakeRunner())
    attach_worker_state(app, state, key)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://state-test",
            headers={"X-API-Key": key},
        ) as client:
            for _ in range(30):
                if (await client.get("/ready")).status_code == 200:
                    break
                await asyncio.sleep(0.01)
            task = asyncio.create_task(client.post("/medical/evaluate", json=payload))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert (await client.get("/ready")).status_code == 200
                assert (await client.get("/experiment/state")).json()[
                    "service_request_lock_held"
                ]
                task.cancel()
                await asyncio.sleep(0.02)
                assert not (await client.get("/experiment/state")).json()["idle"]
            finally:
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            final = (await client.get("/experiment/state")).json()
            assert (
                final["idle"]
                and final["generation_started"] == final["generation_finished"] == 1
            )


@pytest.mark.parametrize(
    "code,idle,expected",
    [
        ("PROVIDER_TIMEOUT", True, False),
        ("PROVIDER_BUSY", True, False),
        ("INFERENCE_FAILED", True, False),
        ("MODEL_OUTPUT_TOTAL_MISMATCH", False, False),
        ("MODEL_OUTPUT_TOTAL_MISMATCH", True, True),
    ],
)
def test_no_followup_after_infrastructure_error_or_busy_worker(code, idle, expected):
    result = {"status": "medical_failed", "stage_error": {"code": code}}
    assert can_continue(result, {"loaded": True, "idle": idle}) is expected


def test_wrong_grade_does_not_gate_continuation():
    assert can_continue(
        {"status": "completed", "medical_evaluation": {"total_score": 2}},
        {"loaded": True, "idle": True},
    )
