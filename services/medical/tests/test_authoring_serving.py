"""One-port authoring contracts, GPU exclusion and adapter restoration, without GPU."""

import contextlib
import copy
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_http import HEADERS, KEY, FakeRunner, wait_ready
from test_pilot_runtime import Model, Tokenizer

from medical_service.app import create_app
from medical_service.authoring import BaseAuthoringRunner, validate_output, validate_request
from medical_service.authoring_contract import SYSTEM, VERSION
from medical_service.config import Settings
from medical_service.validation import ServiceError


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / "base", tmp_path / "adapter", "a" * 64, "b" * 64, KEY, "c" * 64)


@pytest.fixture
def authoring_payload():
    return {
        "version": VERSION,
        "system": SYSTEM,
        "scope": {"question": "Explain synthetic alpha", "max_score": 1.0},
        "evidence": [
            {
                "source_unit_id": "S",
                "source_id": "BOOK",
                "title": "Synthetic",
                "page_start": 1,
                "page_end": 1,
                "content": "Alpha needs condition A.",
            }
        ],
    }


@pytest.fixture
def proposal():
    return {
        "reference_answer": "Alpha needs condition A.",
        "criteria": [
            {"description": "Name condition A", "max_score": 1.0, "source_unit_ids": ["S"]}
        ],
        "insufficient_basis": [],
    }


def test_authoring_uses_existing_service_auth_and_final_schema(
    settings, authoring_payload, proposal
):
    medical, authoring = FakeRunner({}), FakeRunner(proposal)
    with TestClient(create_app(settings, medical, authoring_runner=authoring)) as client:
        wait_ready(client)
        assert client.post("/authoring/propose", json=authoring_payload).status_code == 401
        assert authoring.calls == 0
        response = client.post("/authoring/propose", json=authoring_payload, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["proposal"] == proposal
        assert set(response.json()) == {"proposal", "model_metadata", "timing"}
        assert authoring.calls == 1 and medical.calls == 0


@pytest.mark.parametrize("change", ["system", "empty", "duplicate", "oversized", "pages"])
def test_invalid_authoring_input_cannot_reach_generation(authoring_payload, change):
    payload = copy.deepcopy(authoring_payload)
    if change == "system":
        payload["system"] = "untrusted replacement prompt"
    elif change == "empty":
        payload["evidence"] = []
    elif change == "duplicate":
        payload["evidence"] *= 2
    elif change == "oversized":
        payload["evidence"][0]["content"] = "a" * 6001
    else:
        payload["evidence"][0]["page_end"] = 0
    with pytest.raises(ServiceError, match="AUTHORING_INPUT_INVALID"):
        validate_request(json.dumps(payload).encode())


@pytest.mark.parametrize("change", ["foreign", "score", "non_json"])
def test_invalid_proposal_is_not_returned_or_repaired(authoring_payload, proposal, change):
    if change == "foreign":
        proposal["criteria"][0]["source_unit_ids"] = ["invented"]
    elif change == "score":
        proposal["criteria"][0]["max_score"] = 2
    raw = "private raw invalid generation" if change == "non_json" else json.dumps(proposal)
    with pytest.raises(ServiceError, match="AUTHORING_OUTPUT_INVALID"):
        validate_output(raw, authoring_payload)


def test_authoring_error_does_not_echo_generation(settings, authoring_payload, caplog):
    runner = FakeRunner({})
    runner.raw = "private raw generation " + KEY
    with TestClient(create_app(settings, FakeRunner({}), authoring_runner=runner)) as client:
        wait_ready(client)
        response = client.post("/authoring/propose", json=authoring_payload, headers=HEADERS)
        assert response.status_code == 502
        assert response.json() == {"error": {"code": "AUTHORING_OUTPUT_INVALID"}}
    assert "stage=AUTHORING" in caplog.text
    assert "private raw generation" not in caplog.text and KEY not in caplog.text


def test_authoring_occupies_same_gpu_slot(settings, authoring_payload, proposal):
    gate = threading.Event()
    authoring = FakeRunner(proposal, block_generate=gate)
    medical = FakeRunner({})
    with TestClient(create_app(settings, medical, authoring_runner=authoring)) as client:
        wait_ready(client)
        with ThreadPoolExecutor() as executor:
            first = executor.submit(
                client.post, "/authoring/propose", json=authoring_payload, headers=HEADERS
            )
            try:
                assert authoring.started.wait(timeout=2)
                second = client.post("/authoring/propose", json=authoring_payload, headers=HEADERS)
                assert second.status_code == 429
                assert authoring.calls == 1
                grading = {
                    "question": "Synthetic",
                    "student_answer": "Alpha",
                    "rubric": {
                        "rubric_id": "R",
                        "max_score": 1,
                        "criteria": [
                            {
                                "criterion_id": "C",
                                "description": "Alpha",
                                "max_score": 1,
                                "required_source_unit_ids": ["S"],
                            }
                        ],
                    },
                    "evidence": authoring_payload["evidence"],
                }
                assert (
                    client.post("/medical/evaluate", json=grading, headers=HEADERS).status_code
                    == 429
                )
                assert medical.calls == 0
            finally:
                gate.set()
            assert first.result().status_code == 200


@pytest.mark.parametrize("fail", [False, True])
def test_base_authoring_restores_medical_adapter(monkeypatch, authoring_payload, fail):
    class AdapterModel(Model):
        enabled = True

        @contextlib.contextmanager
        def disable_adapter(self):
            self.enabled = False
            try:
                yield
            finally:
                self.enabled = True

        def generate(self, **kwargs):
            assert self.enabled is False
            if fail:
                raise RuntimeError("synthetic failure")
            return super().generate(**kwargs)

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            inference_mode=contextlib.nullcontext,
            cuda=SimpleNamespace(synchronize=lambda: None),
        ),
    )
    model, tokenizer = AdapterModel(), Tokenizer()
    medical = SimpleNamespace(
        model=model,
        tokenizer=tokenizer,
        settings=SimpleNamespace(max_input_tokens=4096, max_context_tokens=8192),
        metadata={"model_id": "synthetic", "base_config_sha256": "a" * 64},
    )
    runner = BaseAuthoringRunner(medical)
    runner.load()
    assert runner.metadata["adapter_enabled"] is False
    if fail:
        with pytest.raises(RuntimeError):
            runner.generate(authoring_payload)
    else:
        result = runner.generate(authoring_payload)
        assert result.input_tokens == 10 and result.generated_tokens == 3
        assert tokenizer.messages[0] == {"role": "system", "content": SYSTEM}
    assert model.enabled is True
