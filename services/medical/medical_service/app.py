import asyncio
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .runner import PilotRunner, Runner
from .validation import ServiceError, validate_input, validate_output


def create_app(settings: Settings, runner: Runner | None = None):
    runner = runner if runner is not None else PilotRunner(settings)
    state = {"ready": False, "error": "MODEL_LOADING"}
    lock = asyncio.Lock()

    async def load():
        try:
            await asyncio.to_thread(runner.load)
            state.update(ready=True, error=None)
        except ServiceError as exc:
            state.update(ready=False, error=exc.code)
        except Exception:
            state.update(ready=False, error="MODEL_LOAD_FAILED")

    @asynccontextmanager
    async def lifespan(_app):
        # health remains reachable during the one startup load.
        task = asyncio.create_task(load())
        try:
            yield
        finally:
            await task
            async with lock:
                await asyncio.to_thread(runner.close)
            state["ready"] = False

    app = FastAPI(title="MedResident Medical inference", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def service_error(_request, exc):
        # No raw model output, request payload, API key or validation input in error bodies.
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready():
        if not state["ready"]:
            raise ServiceError(state["error"], 503)
        return {"status": "ready"}

    @app.post("/medical/evaluate")
    async def evaluate(request: Request):
        key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(key.encode("utf-8"), settings.api_key.encode("utf-8")):
            raise ServiceError("UNAUTHORIZED", 401)
        if not state["ready"]:
            raise ServiceError(state["error"], 503)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ServiceError("JSON_CONTENT_TYPE_REQUIRED", 415)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > settings.max_body_bytes:
                raise ServiceError("REQUEST_TOO_LARGE", 413)
            body.extend(chunk)
        payload, validated = validate_input(bytes(body))
        if lock.locked():
            raise ServiceError("INFERENCE_BUSY", 429)
        async with lock:
            task = asyncio.create_task(asyncio.to_thread(runner.generate, payload))
            try:
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                # A disconnected caller must not release the GPU slot while generate still runs.
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not task.cancelled():
                    task.exception()  # Consume a failed generation without logging its payload.
                raise
            except ServiceError:
                raise
            except Exception:
                raise ServiceError("INFERENCE_FAILED", 502) from None
            prediction = validate_output(result.text, validated)
            return {
                "medical_evaluation": prediction,
                "model_metadata": runner.metadata,
                "timing": {
                    "inference_seconds": result.inference_seconds,
                    "input_tokens": result.input_tokens,
                    "generated_tokens": result.generated_tokens,
                },
            }

    return app
