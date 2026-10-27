import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from medical_service.app import create_app
from medical_service.config import Settings
from medical_service.runner import Generation
from medical_service.validation import ServiceError

KEY = "synthetic-test-key-123456"
HEADERS = {"X-API-Key": KEY}


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / "base", tmp_path / "adapter", "a" * 64, "b" * 64, KEY, "c" * 64)


@pytest.fixture
def request_data():
    return {
        "question": "Nêu ý alpha.",
        "student_answer": "Đây là câu trả lời thử.",
        "rubric": {
            "rubric_id": "R1",
            "max_score": 1,
            "criteria": [
                {
                    "criterion_id": "C1",
                    "description": "Nêu ý alpha",
                    "max_score": 1,
                    "required_source_unit_ids": ["SU1"],
                    "acceptable_variants": [],
                    "common_incorrect_claims": [],
                }
            ],
        },
        "evidence": [
            {
                "source_unit_id": "SU1",
                "source_id": "SRC1",
                "title": "Nguồn giả",
                "page_start": 1,
                "page_end": 1,
                "content": "Nội dung alpha.",
            }
        ],
    }


@pytest.fixture
def prediction():
    return {
        "correct_points": ["Ý alpha"],
        "incorrect_points": [],
        "missing_points": [],
        "rubric_scores": [
            {
                "criterion_id": "C1",
                "criterion": "Nêu ý alpha",
                "score": 1,
                "max_score": 1,
                "reason": "Phù hợp evidence",
            }
        ],
        "total_score": 1,
        "max_score": 1,
        "sufficient_evidence": True,
        "evidence_refs": ["SU1"],
    }


class FakeRunner:
    def __init__(self, prediction, *, load_error=None, block_load=None, block_generate=None):
        self.raw = json.dumps(prediction, ensure_ascii=False)
        self.metadata = {"model_id": "fake-no-model-loaded", "adapter_sha256": "synthetic"}
        self.loads = self.calls = self.closed = 0
        self.load_error = load_error
        self.block_load = block_load
        self.block_generate = block_generate
        self.started = threading.Event()

    def load(self):
        self.loads += 1
        if self.block_load:
            self.block_load.wait(timeout=5)
        if self.load_error:
            raise self.load_error

    def generate(self, payload):
        self.calls += 1
        self.payload = copy.deepcopy(payload)
        self.started.set()
        if self.block_generate:
            self.block_generate.wait(timeout=5)
        return Generation(self.raw, 0.01, 100, 30)

    def close(self):
        self.closed += 1


def wait_ready(client):
    for _ in range(100):
        if client.get("/ready").status_code == 200:
            return
        time.sleep(0.005)
    pytest.fail("Fake runner failed to become ready")


def test_contract_load_once_and_original_values(settings, request_data, prediction):
    runner = FakeRunner(prediction)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        assert client.get("/health").json() == {"status": "healthy"}
        for _ in range(2):
            response = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
            assert response.status_code == 200
            assert response.json()["medical_evaluation"] == prediction
            assert set(response.json()) == {"medical_evaluation", "model_metadata", "timing"}
        assert runner.payload == request_data
        assert runner.loads == 1 and runner.calls == 2
    assert runner.closed == 1


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_authentication(settings, request_data, prediction, headers):
    runner = FakeRunner(prediction)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        assert (
            client.post("/medical/evaluate", json=request_data, headers=headers).status_code == 401
        )
        assert runner.calls == 0


def test_health_during_loading_and_failed_readiness(settings, request_data, prediction):
    gate = threading.Event()
    runner = FakeRunner(
        prediction, block_load=gate, load_error=ServiceError("ADAPTER_HASH_MISMATCH", 503)
    )
    with TestClient(create_app(settings, runner)) as client:
        try:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").json()["error"]["code"] == "MODEL_LOADING"
        finally:
            gate.set()
        for _ in range(100):
            response = client.get("/ready")
            if response.json()["error"]["code"] == "ADAPTER_HASH_MISMATCH":
                break
            time.sleep(0.005)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ADAPTER_HASH_MISMATCH"
        assert (
            client.post("/medical/evaluate", json=request_data, headers=HEADERS).status_code == 503
        )
        assert runner.calls == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(extra="unsupported"),
        lambda d: d.update(student_answer=" "),
        lambda d: d["rubric"].update(max_score=2),
        lambda d: d["rubric"]["criteria"].append(copy.deepcopy(d["rubric"]["criteria"][0])),
        lambda d: d["evidence"].append(copy.deepcopy(d["evidence"][0])),
        lambda d: d["rubric"]["criteria"][0].update(max_score=True),
        lambda d: d["evidence"][0].update(page_start=2),
    ],
)
def test_invalid_input(settings, request_data, prediction, mutation):
    runner = FakeRunner(prediction)
    mutation(request_data)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        response = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
        assert response.status_code == 422
        assert response.json() == {"error": {"code": "INVALID_REQUEST"}}
        assert runner.calls == 0
        assert "Đây là" not in response.text


@pytest.mark.parametrize(
    "raw", ['{"question":NaN}', '{"question":1e999}', '{"question":"a","question":"b"}', "{bad"]
)
def test_strict_json(settings, prediction, raw):
    runner = FakeRunner(prediction)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        response = client.post(
            "/medical/evaluate",
            content=raw,
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        assert response.status_code == 422 and runner.calls == 0


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda d: d.pop("correct_points"), "MODEL_OUTPUT_INVALID_SCHEMA"),
        (lambda d: d.update(extra=1), "MODEL_OUTPUT_INVALID_SCHEMA"),
        (
            lambda d: d["rubric_scores"][0].update(criterion_id="WRONG"),
            "MODEL_OUTPUT_CRITERION_MISMATCH",
        ),
        (lambda d: d["rubric_scores"].clear(), "MODEL_OUTPUT_CRITERION_MISMATCH"),
        (
            lambda d: d["rubric_scores"].append(copy.deepcopy(d["rubric_scores"][0])),
            "MODEL_OUTPUT_CRITERION_MISMATCH",
        ),
        (lambda d: d["rubric_scores"][0].update(score=2), "MODEL_OUTPUT_SCORE_INVALID"),
        (lambda d: d["rubric_scores"][0].update(score=-1), "MODEL_OUTPUT_SCORE_INVALID"),
        (lambda d: d["rubric_scores"][0].update(max_score=2), "MODEL_OUTPUT_SCORE_INVALID"),
        (lambda d: d.update(total_score=0), "MODEL_OUTPUT_TOTAL_MISMATCH"),
        (lambda d: d.update(max_score=2), "MODEL_OUTPUT_TOTAL_MISMATCH"),
        (lambda d: d.update(evidence_refs=["OTHER_REQUEST"]), "MODEL_OUTPUT_EVIDENCE_INVALID"),
        (lambda d: d.update(evidence_refs=["SU1", "SU1"]), "MODEL_OUTPUT_EVIDENCE_INVALID"),
        (lambda d: d.update(total_score=True), "MODEL_OUTPUT_INVALID_SCHEMA"),
    ],
)
def test_output_rejected_without_repair_or_retry(
    settings, request_data, prediction, mutation, code
):
    mutation(prediction)
    runner = FakeRunner(prediction)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        response = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
        assert response.status_code == 502
        assert response.json() == {"error": {"code": code}}
        assert runner.calls == 1


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        '{"total_score":NaN}',
        '{"total_score":1e999}',
        '{"total_score":1,"total_score":2}',
    ],
)
def test_bad_output_json(settings, request_data, prediction, raw):
    runner = FakeRunner(prediction)
    runner.raw = raw
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        response = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
        assert response.json() == {"error": {"code": "MODEL_OUTPUT_INVALID_JSON"}}
        assert runner.calls == 1


def test_body_limit_and_content_type(settings, request_data, prediction):
    from dataclasses import replace

    runner = FakeRunner(prediction)
    with TestClient(create_app(replace(settings, max_body_bytes=10), runner)) as client:
        wait_ready(client)
        assert (
            client.post("/medical/evaluate", json=request_data, headers=HEADERS).status_code == 413
        )
        assert client.post("/medical/evaluate", content="text", headers=HEADERS).status_code == 415
        assert runner.calls == 0


def test_single_generation_slot(settings, request_data, prediction):
    gate = threading.Event()
    runner = FakeRunner(prediction, block_generate=gate)
    with TestClient(create_app(settings, runner)) as client, ThreadPoolExecutor() as pool:
        wait_ready(client)
        first = pool.submit(client.post, "/medical/evaluate", json=request_data, headers=HEADERS)
        try:
            assert runner.started.wait(timeout=2)
            second = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
            assert second.status_code == 429
            assert runner.calls == 1
        finally:
            gate.set()
        assert first.result().status_code == 200


def test_generation_errors_are_scrubbed_and_not_retried(settings, request_data, prediction):
    class BrokenRunner(FakeRunner):
        def generate(self, payload):
            self.calls += 1
            raise RuntimeError("synthetic sensitive student text must not be returned")

    runner = BrokenRunner(prediction)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        response = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
        assert response.status_code == 502
        assert response.json() == {"error": {"code": "INFERENCE_FAILED"}}
        assert runner.calls == 1


def test_criterion_order_must_match_rubric(settings, request_data, prediction):
    second = copy.deepcopy(request_data["rubric"]["criteria"][0])
    second["criterion_id"] = "C2"
    request_data["rubric"]["criteria"].append(second)
    request_data["rubric"]["max_score"] = 2
    wrong_order = copy.deepcopy(prediction["rubric_scores"][0])
    wrong_order["criterion_id"] = "C2"
    prediction["rubric_scores"].insert(0, wrong_order)
    prediction.update(max_score=2, total_score=2)
    runner = FakeRunner(prediction)
    with TestClient(create_app(settings, runner)) as client:
        wait_ready(client)
        response = client.post("/medical/evaluate", json=request_data, headers=HEADERS)
        assert response.json() == {"error": {"code": "MODEL_OUTPUT_CRITERION_MISMATCH"}}
        assert runner.calls == 1


def test_cancelled_request_keeps_slot_until_generation_finishes(settings, request_data, prediction):
    import asyncio

    import httpx

    gate = threading.Event()
    runner = FakeRunner(prediction, block_generate=gate)
    app = create_app(settings, runner)

    async def scenario():
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://synthetic.local"
            ) as client,
        ):
            async with asyncio.timeout(2):
                while (await client.get("/ready")).status_code != 200:
                    await asyncio.sleep(0.005)
            first = asyncio.create_task(
                client.post("/medical/evaluate", json=request_data, headers=HEADERS)
            )
            try:
                async with asyncio.timeout(2):
                    while not runner.started.is_set():
                        await asyncio.sleep(0.005)
                first.cancel()
                await asyncio.sleep(0.005)
                first.cancel()  # A repeated cancellation must not release the worker slot either.
                await asyncio.sleep(0.005)
                second = await client.post("/medical/evaluate", json=request_data, headers=HEADERS)
                assert second.status_code == 429 and runner.calls == 1
            finally:
                gate.set()
            with pytest.raises(asyncio.CancelledError):
                await first

    asyncio.run(scenario())
