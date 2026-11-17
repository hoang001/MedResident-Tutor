import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings, TeachingSettings
from .runner import PilotRunner, Runner
from .teaching import TeachingRunner, validate_teaching_input, validate_teaching_output
from .validation import ServiceError, validate_input, validate_output

logger = logging.getLogger("uvicorn.error")


def create_app(
    settings: Settings,
    runner: Runner | None = None,
    *,
    teaching_settings: TeachingSettings | None = None,
    teaching_runner: Runner | None = None,
    require_teaching=False,
):
    medical = runner if runner is not None else PilotRunner(settings)
    if teaching_settings and teaching_settings.api_key != settings.api_key:
        raise ValueError("One model service requires one shared API key")
    teaching = (
        teaching_runner
        if teaching_runner is not None
        else (TeachingRunner(teaching_settings) if teaching_settings else None)
    )
    if require_teaching and teaching is None:
        raise ValueError("Unified serving requires Teaching configuration")
    runners = {"medical": medical}
    if teaching is not None:
        runners["teaching"] = teaching
    state = {"ready": False, "error": "MODEL_LOADING"}
    # One lock for ALL GPU generation, including cancelled/disconnected requests.
    lock = asyncio.Lock()

    async def load():
        for name, model in runners.items():
            logger.info("%s model loading", name.upper())
            try:
                await asyncio.to_thread(model.load)
            except ServiceError as exc:
                code = name.upper() + "_" + exc.code if len(runners) > 1 else exc.code
                state.update(ready=False, error=code)
                logger.error("Model readiness failed: %s", code)
                return
            except Exception as exc:
                code = (
                    name.upper() + "_MODEL_LOAD_FAILED" if len(runners) > 1 else "MODEL_LOAD_FAILED"
                )
                state.update(ready=False, error=code)
                logger.error("Model readiness failed: %s; error_type=%s", code, type(exc).__name__)
                return
            logger.info("%s model loaded", name.upper())
        state.update(ready=True, error=None)
        logger.info("All configured models ready")

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(load())
        try:
            yield
        finally:
            await task
            async with lock:
                for model in reversed(list(runners.values())):
                    await asyncio.to_thread(model.close)
            state["ready"] = False

    app = FastAPI(title="MedResident Medical and Teaching inference", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def service_error(_request, exc):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready():
        if not state["ready"]:
            raise ServiceError(state["error"], 503)
        return {"status": "ready"}

    async def evaluate(request: Request, stage: str):
        key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(key.encode("utf-8"), settings.api_key.encode("utf-8")):
            raise ServiceError("UNAUTHORIZED", 401)
        if stage not in runners:
            raise ServiceError("TEACHING_NOT_CONFIGURED", 503)
        if not state["ready"]:
            raise ServiceError(state["error"], 503)
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise ServiceError("JSON_CONTENT_TYPE_REQUIRED", 415)
        limit = (
            teaching_settings.max_body_bytes
            if stage == "teaching" and teaching_settings
            else settings.max_body_bytes
        )
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                raise ServiceError("REQUEST_TOO_LARGE", 413)
            body.extend(chunk)
        if stage == "medical":
            payload, validated = validate_input(bytes(body))
        else:
            payload = validated = validate_teaching_input(bytes(body))
        if lock.locked():
            raise ServiceError("INFERENCE_BUSY", 429)
        model = runners[stage]
        async with lock:
            task = asyncio.create_task(asyncio.to_thread(model.generate, payload))
            try:
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                # Do not release the shared GPU slot while its thread still generates.
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not task.cancelled():
                    task.exception()
                raise
            except ServiceError:
                raise
            except Exception:
                raise ServiceError("INFERENCE_FAILED", 502) from None
            prediction = (
                validate_output(result.text, validated)
                if stage == "medical"
                else validate_teaching_output(result.text, validated)
            )
            return {
                "medical_evaluation" if stage == "medical" else "teaching_feedback": prediction,
                "model_metadata": model.metadata,
                "timing": {
                    "inference_seconds": result.inference_seconds,
                    "input_tokens": result.input_tokens,
                    "generated_tokens": result.generated_tokens,
                },
            }

    @app.post("/medical/evaluate")
    async def medical_evaluate(request: Request):
        return await evaluate(request, "medical")

    @app.post("/teaching/feedback")
    async def teaching_feedback(request: Request):
        return await evaluate(request, "teaching")

    return app
