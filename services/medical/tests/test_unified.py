"""HTTP/state/guard checks with fake runners, never GPU or locked datasets."""

import asyncio
import contextlib
import copy
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_http import HEADERS, KEY, FakeRunner, wait_ready

from medical_service.app import create_app
from medical_service.config import Settings, TeachingSettings
from medical_service.runner import Generation
from medical_service.teaching import (
    MODEL_ID,
    SYSTEM_PROMPT,
    TeachingRunner,
    validate_teaching_input,
    validate_teaching_output,
)
from medical_service.validation import ServiceError


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / "base", tmp_path / "adapter", "a" * 64, "b" * 64, KEY, "c" * 64)


@pytest.fixture
def medical_input():
    return {
        "question": "Synthetic alpha?",
        "student_answer": "Synthetic alpha.",
        "rubric": {
            "rubric_id": "R",
            "max_score": 1,
            "criteria": [
                {
                    "criterion_id": "C",
                    "description": "Alpha anchor",
                    "max_score": 1,
                    "required_source_unit_ids": ["S"],
                }
            ],
        },
        "evidence": [
            {
                "source_unit_id": "S",
                "source_id": "BOOK",
                "title": "Synthetic",
                "page_start": 1,
                "page_end": 1,
                "content": "Alpha anchor",
            }
        ],
    }


@pytest.fixture
def medical_output():
    return {
        "correct_points": ["Alpha anchor"],
        "incorrect_points": [],
        "missing_points": [],
        "rubric_scores": [
            {
                "criterion_id": "C",
                "criterion": "Alpha anchor",
                "score": 1,
                "max_score": 1,
                "reason": "Alpha anchor",
            }
        ],
        "total_score": 1,
        "max_score": 1,
        "sufficient_evidence": True,
        "evidence_refs": ["S"],
    }


@pytest.fixture
def teaching_input(medical_input, medical_output):
    return {
        "schema_version": "1.0.0",
        "question": medical_input["question"],
        "student_answer": medical_input["student_answer"],
        "medical_evaluation": medical_output,
        "learner_context": {
            "mastery": [],
            "recurring_errors": [],
            "recent_improvements": [],
            "recent_attempts_summary": None,
        },
        "metadata": {
            "specialty": None,
            "course_group": None,
            "course_id": None,
            "course_name": None,
            "specialty_level": None,
            "topic_id": None,
            "topic_name": None,
            "concept_ids": [],
        },
    }


@pytest.fixture
def teaching_output():
    return {
        "strengths": ["Alpha anchor"],
        "corrections": [],
        "missing_focus": [],
        "learning_priority": [],
        "feedback_text": "Alpha anchor.",
        "follow_up_question": None,
    }


def test_both_endpoints_use_independent_runners_and_preserve_medical(
    settings, medical_input, medical_output, teaching_input, teaching_output
):
    med, teach = FakeRunner(medical_output), FakeRunner(teaching_output)
    original = copy.deepcopy(teaching_input)
    with TestClient(
        create_app(settings, med, teaching_runner=teach, require_teaching=True)
    ) as client:
        wait_ready(client)
        assert client.get("/health").json() == {"status": "healthy"}
        assert (
            client.post("/medical/evaluate", json=medical_input, headers=HEADERS).json()[
                "medical_evaluation"
            ]
            == medical_output
        )
        response = client.post("/teaching/feedback", json=teaching_input, headers=HEADERS)
        assert response.status_code == 200, response.text
        assert response.json()["teaching_feedback"] == teaching_output
        assert set(response.json()) == {"teaching_feedback", "model_metadata", "timing"}
        assert "total_score" not in response.json()["teaching_feedback"]
        assert teaching_input == original
    assert med.loads == teach.loads == med.calls == teach.calls == med.closed == teach.closed == 1


def test_readiness_waits_for_both_and_failure_is_stage_specific(
    settings, medical_input, medical_output, teaching_output
):
    gate = threading.Event()
    teaching = FakeRunner(
        teaching_output, block_load=gate, load_error=ServiceError("ADAPTER_HASH_MISMATCH", 503)
    )
    with TestClient(
        create_app(
            settings, FakeRunner(medical_output), teaching_runner=teaching, require_teaching=True
        )
    ) as client:
        try:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503
            assert (
                client.post("/medical/evaluate", json=medical_input, headers=HEADERS).status_code
                == 503
            )
        finally:
            gate.set()
        import time

        for _ in range(100):
            response = client.get("/ready")
            if response.json()["error"]["code"] == "TEACHING_ADAPTER_HASH_MISMATCH":
                break
            time.sleep(0.005)
        assert response.json() == {"error": {"code": "TEACHING_ADAPTER_HASH_MISMATCH"}}
        assert teaching.calls == 0


@pytest.mark.parametrize("blocked_stage", ["medical", "teaching"])
def test_one_gpu_lock_covers_both_routes(
    settings, medical_input, medical_output, teaching_input, teaching_output, blocked_stage
):
    gate = threading.Event()
    med = FakeRunner(medical_output, block_generate=gate if blocked_stage == "medical" else None)
    teach = FakeRunner(
        teaching_output, block_generate=gate if blocked_stage == "teaching" else None
    )
    runners = {"medical": med, "teaching": teach}
    paths = {"medical": "/medical/evaluate", "teaching": "/teaching/feedback"}
    payloads = {"medical": medical_input, "teaching": teaching_input}
    other = "teaching" if blocked_stage == "medical" else "medical"
    with (
        TestClient(
            create_app(settings, med, teaching_runner=teach, require_teaching=True)
        ) as client,
        ThreadPoolExecutor() as pool,
    ):
        wait_ready(client)
        first = pool.submit(
            client.post, paths[blocked_stage], json=payloads[blocked_stage], headers=HEADERS
        )
        try:
            assert runners[blocked_stage].started.wait(timeout=2)
            response = client.post(paths[other], json=payloads[other], headers=HEADERS)
            assert response.status_code == 429 and runners[other].calls == 0
        finally:
            gate.set()
        assert first.result().status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_teaching_authentication(
    settings, medical_output, teaching_input, teaching_output, headers
):
    teach = FakeRunner(teaching_output)
    with TestClient(
        create_app(settings, FakeRunner(medical_output), teaching_runner=teach)
    ) as client:
        wait_ready(client)
        assert (
            client.post("/teaching/feedback", json=teaching_input, headers=headers).status_code
            == 401
        )
        assert teach.calls == 0


@pytest.mark.parametrize(
    "raw", ["not-json", '{"schema_version":NaN}', '{"question":"a","question":"b"}']
)
def test_teaching_strict_input(settings, medical_output, teaching_output, raw):
    teach = FakeRunner(teaching_output)
    with TestClient(
        create_app(settings, FakeRunner(medical_output), teaching_runner=teach)
    ) as client:
        wait_ready(client)
        assert (
            client.post(
                "/teaching/feedback",
                content=raw,
                headers={**HEADERS, "Content-Type": "application/json"},
            ).status_code
            == 422
        )
        assert client.post("/teaching/feedback", content=raw, headers=HEADERS).status_code == 415
        assert teach.calls == 0


@pytest.mark.parametrize("mutation", ["score", "anchor", "extra_input", "nan_anchor"])
def test_invalid_teaching_payload_or_output_is_not_repaired(
    teaching_input, teaching_output, mutation
):
    payload = copy.deepcopy(teaching_input)
    out = copy.deepcopy(teaching_output)
    if mutation == "extra_input":
        payload["evidence"] = []
        with pytest.raises(ServiceError, match="TEACHING_INPUT_INVALID"):
            validate_teaching_input(json.dumps(payload).encode())
    elif mutation == "nan_anchor":
        payload["medical_evaluation"]["total_score"] = float("nan")
        with pytest.raises(ServiceError, match="TEACHING_INPUT_INVALID"):
            validate_teaching_input(json.dumps(payload).encode())
    else:
        if mutation == "score":
            out["total_score"] = 0
        else:
            out["strengths"] = ["Different invented information"]
        with pytest.raises(ServiceError):
            validate_teaching_output(json.dumps(out), payload)


def test_guards_are_reused_without_mutating_anchor(teaching_input, teaching_output):
    teaching_input["medical_evaluation"]["sufficient_evidence"] = False
    original = copy.deepcopy(teaching_input)
    result = validate_teaching_output(json.dumps(teaching_output), teaching_input)
    assert "không đủ" in result["feedback_text"]
    assert teaching_input == original


def test_production_factory_requires_teaching_and_one_key(settings, medical_output, tmp_path):
    with pytest.raises(ValueError, match="requires Teaching"):
        create_app(settings, FakeRunner(medical_output), require_teaching=True)
    other = TeachingSettings(
        tmp_path / "t-base",
        tmp_path / "t-adapter",
        "a" * 64,
        "b" * 64,
        "another-valid-test-key",
        "c" * 64,
    )
    with pytest.raises(ValueError, match="shared API key"):
        create_app(settings, FakeRunner(medical_output), teaching_settings=other)


@pytest.mark.parametrize(
    "raw", ["private raw output", "```json\n{}\n```", '{"strengths":[],"strengths":[]}']
)
def test_teaching_http_never_returns_invalid_raw_generation(
    settings, medical_output, teaching_input, teaching_output, raw, caplog
):
    class RawTeaching(FakeRunner):
        def generate(self, payload):
            self.calls += 1
            return Generation(raw, 0.1, 10, 5)

    teach = RawTeaching(teaching_output)
    with TestClient(
        create_app(settings, FakeRunner(medical_output), teaching_runner=teach)
    ) as client:
        wait_ready(client)
        response = client.post("/teaching/feedback", json=teaching_input, headers=HEADERS)
        assert response.status_code == 502
        assert set(response.json()) == {"error"}
        assert raw not in response.text and KEY not in response.text
        assert response.headers["X-Model-Error-Code"] == response.json()["error"]["code"]
        assert "stage=TEACHING" in caplog.text and "phase=json_parse" in caplog.text
        assert raw not in caplog.text and KEY not in caplog.text
        assert teach.calls == 1


def test_alignment_failure_logs_only_check_names(
    settings, medical_output, teaching_input, teaching_output, caplog
):
    teaching_output["strengths"] = ["private unrelated model-generated information"]
    with TestClient(create_app(
        settings, FakeRunner(medical_output), teaching_runner=FakeRunner(teaching_output)
    )) as client:
        wait_ready(client)
        response = client.post("/teaching/feedback", json=teaching_input, headers=HEADERS)
        assert response.status_code == 502
        assert response.json() == {"error": {"code": "TEACHING_ALIGNMENT_INVALID"}}
    assert "phase=alignment_validation" in caplog.text
    assert "strengths_consistency" in caplog.text
    assert "private unrelated" not in caplog.text and KEY not in caplog.text


def test_generation_failure_logs_type_without_exception_text(
    settings, medical_output, teaching_input, teaching_output, caplog
):
    class BrokenTeaching(FakeRunner):
        def generate(self, payload):
            raise RuntimeError("private generation exception " + KEY)

    with TestClient(create_app(
        settings, FakeRunner(medical_output), teaching_runner=BrokenTeaching(teaching_output)
    )) as client:
        wait_ready(client)
        response = client.post("/teaching/feedback", json=teaching_input, headers=HEADERS)
        assert response.status_code == 502
        assert response.json() == {"error": {"code": "INFERENCE_FAILED"}}
    assert "phase=generation" in caplog.text and "error_type=RuntimeError" in caplog.text
    assert "private generation" not in caplog.text and KEY not in caplog.text


def test_model_load_error_log_does_not_contain_exception_or_key(
    settings, medical_output, teaching_output, caplog
):
    class BrokenTeaching(FakeRunner):
        def load(self):
            raise RuntimeError("private load details " + KEY)

    with TestClient(
        create_app(
            settings, FakeRunner(medical_output), teaching_runner=BrokenTeaching(teaching_output)
        )
    ) as client:
        import time

        for _ in range(100):
            response = client.get("/ready")
            if response.json()["error"]["code"] == "TEACHING_MODEL_LOAD_FAILED":
                break
            time.sleep(0.005)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "TEACHING_MODEL_LOAD_FAILED"
    assert KEY not in caplog.text and "private load details" not in caplog.text


@pytest.mark.parametrize("stage", ["medical", "teaching"])
def test_cancellation_keeps_shared_slot(
    settings, medical_input, medical_output, teaching_input, teaching_output, stage
):
    import httpx

    gate = threading.Event()
    runners = {
        "medical": FakeRunner(medical_output, block_generate=gate if stage == "medical" else None),
        "teaching": FakeRunner(
            teaching_output, block_generate=gate if stage == "teaching" else None
        ),
    }
    paths = {"medical": "/medical/evaluate", "teaching": "/teaching/feedback"}
    payloads = {"medical": medical_input, "teaching": teaching_input}
    other = "teaching" if stage == "medical" else "medical"
    app = create_app(settings, runners["medical"], teaching_runner=runners["teaching"])

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
                client.post(paths[stage], json=payloads[stage], headers=HEADERS)
            )
            try:
                async with asyncio.timeout(2):
                    while not runners[stage].started.is_set():
                        await asyncio.sleep(0.005)
                first.cancel()
                await asyncio.sleep(0.005)
                second = await client.post(paths[other], json=payloads[other], headers=HEADERS)
                assert second.status_code == 429 and runners[other].calls == 0
            finally:
                gate.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert (
                await client.post(paths[other], json=payloads[other], headers=HEADERS)
            ).status_code == 200

    asyncio.run(scenario())


def test_teaching_local_loading_and_generation_without_gpu(tmp_path, monkeypatch, teaching_input):
    from test_pilot_runtime import Model, Tokenizer

    base, adapter = tmp_path / "base", tmp_path / "adapter"
    base.mkdir()
    adapter.mkdir()
    (base / "config.json").write_text('{"model_type":"qwen2"}')
    (base / "tokenizer_config.json").write_text("{}")
    (base / "model.safetensors").write_bytes(b"synthetic-only")
    (adapter / "adapter_model.safetensors").write_bytes(b"synthetic-only")
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": MODEL_ID,
                "peft_type": "LORA",
                "task_type": "CAUSAL_LM",
            }
        )
    )

    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    config = TeachingSettings(
        base,
        adapter,
        sha(adapter / "adapter_model.safetensors"),
        sha(base / "config.json"),
        KEY,
        sha(adapter / "adapter_config.json"),
    )
    runner = TeachingRunner(config)
    tokenizer, model = Tokenizer(), Model()
    tokenizer.chat_template = "synthetic template"
    model.eval = lambda: model
    calls = {}

    def loader(name, result):
        def load(*args, **kwargs):
            calls[name] = (args, kwargs)
            return result

        return SimpleNamespace(from_pretrained=load)

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            float16="stub-float16",
            inference_mode=contextlib.nullcontext,
            cuda=SimpleNamespace(is_available=lambda: True, synchronize=lambda: None),
        ),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=loader("adapter", model)))
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=loader("tokenizer", tokenizer),
            AutoModelForCausalLM=loader("base", model),
            BitsAndBytesConfig=lambda **kwargs: kwargs,
            set_seed=lambda seed: calls.update(seed=seed),
        ),
    )
    monkeypatch.setattr(
        "medical_service.teaching.importlib.metadata.version", lambda _: "synthetic"
    )
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    runner.load()
    assert os.environ["HF_HUB_OFFLINE"] == os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert calls["seed"] == 42
    assert all(calls[name][1]["local_files_only"] for name in ("base", "adapter", "tokenizer"))
    assert calls["base"][1]["quantization_config"] == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "stub-float16",
        "bnb_4bit_use_double_quant": True,
    }
    assert calls["adapter"][1]["is_trainable"] is False
    assert calls["base"][1]["attn_implementation"] == "sdpa"
    result = runner.generate(teaching_input)
    assert result.input_tokens == 10 and result.generated_tokens == 3
    assert tokenizer.messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert json.loads(tokenizer.messages[1]["content"]) == {
        k: v for k, v in teaching_input.items() if k != "schema_version"
    }
    assert {k: v for k, v in model.kwargs.items() if k != "input_ids"} == {
        "max_new_tokens": 1600,
        "do_sample": False,
        "temperature": 0.0,
        "pad_token_id": 0,
    }
    from dataclasses import replace

    runner.settings = replace(config, max_input_tokens=9)
    with pytest.raises(ServiceError, match="INPUT_TOKEN_LIMIT"):
        runner.generate(teaching_input)
    assert model.calls == 1
    (adapter / "adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(ServiceError, match="ADAPTER_HASH_MISMATCH"):
        runner.load()
    runner.close()
