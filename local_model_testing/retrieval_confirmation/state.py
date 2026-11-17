"""Observe the actual V1 serving lock, including a cancelled caller's generation."""

import inspect
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse


def attach_worker_state(app, state, api_key):
    endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", None) == "/medical/evaluate"
    )
    service_lock = inspect.getclosurevars(endpoint).nonlocals["lock"]

    @app.get("/experiment/state")
    async def worker_state(request: Request):
        supplied = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(supplied.encode(), api_key.encode()):
            return JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)
        started = list(state.get("generation_attempt_ids", []))
        finished = list(state.get("generation_finished_ids", []))
        return {
            "loaded": state.get("status") == "ready",
            "service_request_lock_held": service_lock.locked(),
            "active_runner_trace_id": state.get("active_runner_trace_id"),
            "generation_started": len(started),
            "generation_finished": len(finished),
            "generation_attempt_ids": started,
            "generation_finished_ids": finished,
            "idle": (
                not service_lock.locked()
                and not state.get("active_runner_trace_id")
                and len(started) == len(finished)
            ),
        }

    return service_lock


def can_continue(result, worker):
    if not worker.get("loaded") or not worker.get("idle"):
        return False
    if result["status"] != "medical_failed":
        return True
    code = (result.get("stage_error") or {}).get("code", "")
    return code.startswith("MODEL_OUTPUT_")
