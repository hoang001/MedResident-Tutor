"""Serve the existing Medical API around an already-loaded, verified V1 runner."""

from medical_service.app import create_app
from medical_service.runner import check_artifacts
from medical_service.validation import ServiceError
from contextvars import ContextVar
import hashlib
import json
import uuid

from .common import REPORT, write, read

REQUEST_ID = ContextVar("local_medical_request_id", default="untracked")


def serve(runner, settings):
    import uvicorn

    traced = (REPORT / "generation-budget.json").exists()
    original_generate = runner.model.generate

    def capture_generate(*args, **kwargs):
        request_id = REQUEST_ID.get()
        if traced:
            budget = read(REPORT / "generation-budget.json")
            if budget["calls_started"] >= budget["limit"]:
                raise ServiceError("GENERATION_BUDGET_EXHAUSTED", 429)
            budget["calls_started"] += 1
            write(REPORT / "generation-budget.json", budget)
        output = original_generate(
            *args, **kwargs
        )  # Same arguments; no sampling/model/prompt change.
        if traced:
            prompt_ids = kwargs["input_ids"][0].detach().cpu().tolist()
            tokens = output[0, len(prompt_ids) :].detach().cpu().tolist()
            eos = kwargs.get(
                "eos_token_id", runner.model.generation_config.eos_token_id
            )
            eos_ids = eos if isinstance(eos, list) else [eos]
            limit = kwargs["max_new_tokens"]
            write(
                REPORT / "http-token-traces" / (request_id + ".json"),
                {
                    "request_id": request_id,
                    "input_tokens": len(prompt_ids),
                    "generated_tokens": len(tokens),
                    "input_token_ids_sha256": hashlib.sha256(
                        json.dumps(prompt_ids).encode()
                    ).hexdigest(),
                    "actual_decoded_prompt": runner.tokenizer.decode(
                        prompt_ids, skip_special_tokens=False
                    ),
                    "last_generated_token_id": tokens[-1] if tokens else None,
                    "eos_token_ids": eos_ids,
                    "max_new_tokens": limit,
                    "token_limit_hit": len(tokens) >= limit,
                    "finish_reason": "eos"
                    if tokens and tokens[-1] in eos_ids
                    else "length"
                    if len(tokens) >= limit
                    else "unknown",
                },
            )
            budget = read(REPORT / "generation-budget.json")
            budget["calls_finished"] += 1
            write(REPORT / "generation-budget.json", budget)
        return output

    if traced:
        runner.model.generate = capture_generate

    class LoadedRunner:
        metadata = runner.metadata

        def load(self):
            if runner.model is None:
                raise RuntimeError("MODEL_NOT_LOADED")
            check_artifacts(settings)

        def generate(self, payload):
            result = runner.generate(payload)
            write(
                REPORT / "http-generations" / (REQUEST_ID.get() + ".json")
                if traced
                else REPORT / "medical-http-generation.json",
                {
                    "input": payload,
                    "raw": vars(result),
                    "model_metadata": runner.metadata,
                    "execution": "local_real_adapter_http",
                    "request_id": REQUEST_ID.get(),
                },
            )
            return result

        def close(self):
            # Lifetime/model cleanup belongs to the enclosing owned worker finally.
            pass

    app = create_app(settings, LoadedRunner())

    @app.middleware("http")
    async def request_trace(request, call_next):
        try:
            request_id = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
        except ValueError:
            request_id = str(uuid.uuid4())
        token = REQUEST_ID.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            REQUEST_ID.reset(token)

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8101,
            workers=1,
            access_log=False,
            log_level="error",
        )
    finally:
        if traced:
            runner.model.generate = original_generate
