"""CPU fixtures verify logging preserves generation and enforces the run budget."""
# ruff: noqa: E402

import asyncio
import json
import sys
import uuid

import httpx

from local_model_testing.common import ROOT, REPORT_BASE, read, write

sys.path[:0] = [
    str(ROOT / "model-training"),
    str(ROOT / "services/medical"),
    str(ROOT / "apps/backend"),
]
from local_model_testing import http_service
from medical_service.config import Settings
from medical_service.runner import Generation
from app.modules.practice.providers import MockProvider


class Tensor:
    def __init__(self, ids):
        self.ids = ids

    def __getitem__(self, key):
        if isinstance(key, tuple):
            return Tensor(self.ids[key[1]])
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.ids


def test_logged_http_generation_is_unchanged_and_bounded(tmp_path, monkeypatch):
    import uvicorn

    monkeypatch.setattr(http_service, "REPORT", tmp_path)
    monkeypatch.setattr(http_service, "check_artifacts", lambda settings: {})
    write(
        tmp_path / "generation-budget.json",
        dict(limit=4, calls_started=0, calls_finished=0),
    )
    payload = read(REPORT_BASE / "inputs/CLINICAL_DEMO_V1_CASE01__full.json")
    output, _ = asyncio.run(MockProvider().evaluate("medical", payload))
    calls = []

    class Model:
        generation_config = type("Config", (), {"eos_token_id": [151645]})()

        def generate(self, **kwargs):
            calls.append(kwargs)
            return Tensor([10, 11, 100, 151645])

    class Tokenizer:
        def decode(self, ids, **kwargs):
            return "fixture-prompt"

    class Runner:
        metadata = {"test_fixture_only": True}
        tokenizer = Tokenizer()
        model = Model()

        def generate(self, body):
            result = self.model.generate(
                input_ids=Tensor([10, 11]),
                max_new_tokens=1200,
                do_sample=False,
                eos_token_id=[151645],
            )
            assert result.ids == [10, 11, 100, 151645]
            return Generation(json.dumps(output), 0.01, 2, 2)

    runner = Runner()
    config = Settings(
        base_path=ROOT,
        adapter_path=ROOT,
        adapter_sha256="0" * 64,
        base_config_sha256="0" * 64,
        adapter_config_sha256="0" * 64,
        api_key="unit-fixture-credential-only",
    )

    async def requests(app):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://fixture"
            ) as client:
                while (await client.get("/ready")).status_code != 200:
                    await asyncio.sleep(0.001)
                for i in range(5):
                    rid = str(uuid.uuid4())
                    response = await client.post(
                        "/medical/evaluate",
                        json=payload,
                        headers={"X-API-Key": config.api_key, "X-Request-ID": rid},
                    )
                    assert response.status_code == (200 if i < 4 else 429)
                    if i < 4:
                        assert response.json()["medical_evaluation"] == output
                        trace = read(tmp_path / "http-token-traces" / (rid + ".json"))
                        assert (
                            trace["request_id"] == rid
                            and trace["finish_reason"] == "eos"
                        )
                        assert (
                            not trace["token_limit_hit"] and trace["input_tokens"] == 2
                        )

    monkeypatch.setattr(
        uvicorn, "run", lambda app, **kwargs: asyncio.run(requests(app))
    )
    original = runner.model.generate
    http_service.serve(runner, config)
    assert runner.model.generate == original and len(calls) == 4
    assert all(c["do_sample"] is False and c["max_new_tokens"] == 1200 for c in calls)
    assert read(tmp_path / "generation-budget.json") == dict(
        limit=4, calls_started=4, calls_finished=4
    )
