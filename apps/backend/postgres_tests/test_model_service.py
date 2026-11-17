"""Real PostgreSQL orchestration with a synthetic HTTP boundary, never a GPU."""

import copy
import json
import uuid

import httpx
from sqlalchemy import func, select

from app.ai.model_service import ModelServiceClient
from app.core.config import Settings
from app.modules.practice import router as routes
from app.modules.practice.models import PracticeAttempt
from app.modules.practice.providers import MockProvider, RunPodProvider
from app.modules.practice.service import digest, learner_context
from app.modules.progress.models import LearningResult
from postgres_tests.test_question_bank import BODY
from postgres_tests.test_question_bank import bank as bank_fixture  # noqa: F401


async def test_runpod_http_persistence_retry_and_context(bank_fixture, monkeypatch):  # noqa: F811
    client, factory, state, admin, learner = bank_fixture
    created = (await client.post("/api/v1/admin/questions", json=BODY)).json()
    qid = created["question_id"]
    published = await client.patch(
        f"/api/v1/admin/questions/{qid}/availability",
        json={"version": created["version"], "is_available": True},
    )
    assert published.status_code == 200, published.text
    state["user"] = learner
    settings = Settings(
        _env_file=None,
        model_calls_enabled=True,
        practice_provider="runpod",
        model_service_base_url="https://synthetic.example.invalid/",
        model_service_api_key="synthetic-test-key-only",
    )
    fixture_outputs = MockProvider()
    captured = []
    fail_teaching = False

    async def respond(request):
        nonlocal fail_teaching
        assert request.headers["X-API-Key"] == settings.model_service_api_key
        assert uuid.UUID(request.headers["X-Request-ID"])
        payload = json.loads(request.content)
        stage = "medical" if request.url.path == "/medical/evaluate" else "teaching"
        assert request.url.path in {"/medical/evaluate", "/teaching/feedback"}
        captured.append((stage, copy.deepcopy(payload)))
        if stage == "teaching" and fail_teaching:
            fail_teaching = False
            return httpx.Response(503, json={"error": {"code": "MODEL_LOADING"}})
        output, _ = await fixture_outputs.evaluate(stage, payload)
        if stage == "teaching" and payload["learner_context"]["recent_attempts_summary"]:
            output["feedback_text"] += " Learner context contains prior practice counts."
        field = "medical_evaluation" if stage == "medical" else "teaching_feedback"
        return httpx.Response(
            200,
            json={field: output, "model_metadata": {"fixture": True}, "timing": {}},
        )

    provider = RunPodProvider(settings)
    provider.client = ModelServiceClient(settings, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(routes, "get_provider", lambda *_: provider)
    body = {"question_id": qid, "student_answer": "Synthetic learner response"}
    path = "/api/v1/practice/attempts"

    first = await client.post(path, json=body, headers={"Idempotency-Key": "first"})
    assert first.status_code == 200, first.text
    a = first.json()
    assert a["status"] == "completed" and a["execution_mode"] == "http"
    assert len(captured) == 2
    med_payload, teaching = captured[0][1], captured[1][1]
    assert med_payload["evidence"] and med_payload["rubric"]["criteria"]
    assert teaching["medical_evaluation"] == a["medical_evaluation"]
    assert "evidence" not in teaching and "rubric" not in teaching
    assert teaching["learner_context"]["recent_attempts_summary"] is None
    assert a["provider_metadata"]["medical"]["provider"] == "runpod"
    assert "total_score" not in a["teaching_feedback"]

    mock = MockProvider()
    monkeypatch.setattr(routes, "get_provider", lambda *_: mock)
    mock_result = await client.post(path, json=body, headers={"Idempotency-Key": "mock-history"})
    assert mock_result.json()["status"] == "completed"
    monkeypatch.setattr(routes, "get_provider", lambda *_: provider)

    fail_teaching = True
    second = (await client.post(path, json=body, headers={"Idempotency-Key": "second"})).json()
    assert second["status"] == "teaching_failed"
    assert second["medical_evaluation"] == a["medical_evaluation"]
    assert second["teaching_feedback"] is None
    assert second["stage_error"] == {
        "stage": "teaching",
        "code": "MODEL_SERVICE_NOT_READY",
        "upstream_http_status": 503,
        "upstream_code": "MODEL_LOADING",
    }
    frozen_teaching = captured[-1][1]
    assert "correct_points_count" in frozen_teaching["learner_context"]["recent_attempts_summary"]
    assert (
        frozen_teaching["learner_context"]["recent_attempts_summary"].count('"correct_points_count"')
        == 1
    )
    async with factory() as session:
        row = await session.get(PracticeAttempt, uuid.UUID(second["id"]))
        assert row.snapshot["hash"] == digest(
            {k: v for k, v in row.snapshot.items() if k != "hash"}
        )
        assert row.snapshot["learner_context"] == frozen_teaching["learner_context"]
        # No cross-user or mock/structured history is used.
        assert (await learner_context(session, admin))["recent_attempts_summary"] is None
        assert await session.scalar(select(func.count()).select_from(LearningResult)) == 0

    # New real history arriving while the second attempt is failed cannot change
    # that attempt's frozen Teaching context when explicitly retried.
    third = await client.post(path, json=body, headers={"Idempotency-Key": "third"})
    assert third.json()["status"] == "completed"
    before = len(captured)
    replay = (await client.post(path, json=body, headers={"Idempotency-Key": "second"})).json()
    reload = (await client.get(path + "/" + second["id"])).json()
    assert replay == reload == second and len(captured) == before
    retry = (await client.post(path + "/" + second["id"] + "/retry")).json()
    assert retry["status"] == "completed"
    assert retry["medical_evaluation"] == second["medical_evaluation"]
    assert retry["snapshot_hash"] == second["snapshot_hash"]
    assert captured[-1] == ("teaching", frozen_teaching)
    assert [s for s, _ in captured] == [
        "medical",
        "teaching",
        "medical",
        "teaching",
        "medical",
        "teaching",
        "teaching",
    ]

    state["user"] = admin
    assert (await client.get(path + "/" + retry["id"])).status_code == 404
    assert (await client.post(path + "/" + retry["id"] + "/retry")).status_code == 404
