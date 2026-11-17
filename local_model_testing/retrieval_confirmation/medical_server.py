"""Same locked Medical runner/API, with request/prompt trace and shared-ledger guard."""

import gc
import os
import sys
import time
import uuid
from contextvars import ContextVar

from . import ledger
from .common import ROOT, RUN, read, write, digest, file_hash, system_snapshot
from .state import attach_worker_state

CONTEXT = ContextVar("retrieval_medical_trace", default=None)


def main():
    sys.path.insert(0, str(ROOT / "model-training"))
    sys.path.insert(0, str(ROOT / "services/medical"))
    sys.path.insert(0, str(ROOT / "apps/backend"))
    from medical_service.app import create_app
    from medical_service.config import Settings
    from medical_service.runner import PilotRunner
    from medical_service.validation import ServiceError
    from local_model_testing.artifacts import check
    from local_model_testing.worker import check_capacity
    from app.ai.retrieval.evidence import evidence_identities, verify_payload_evidence
    import uvicorn

    artifact = read(ROOT / "data/local-models/locked-adapters.json")["medical"]
    settings = Settings(
        base_path=ROOT / "data/local-models/base/Qwen3-4B-Instruct-2507",
        adapter_path=ROOT / artifact["adapter_path"],
        adapter_sha256=artifact["adapter_sha256"],
        adapter_config_sha256=artifact["adapter_config_sha256"],
        base_config_sha256=file_hash(
            ROOT / "data/local-models/base/Qwen3-4B-Instruct-2507/config.json"
        ),
        api_key=os.environ["MEDICAL_API_KEY"],
    )
    inner = PilotRunner(settings)
    state = {
        "status": "starting",
        "pid": os.getpid(),
        "before": system_snapshot(),
        "generation_attempt_ids": [],
        "generation_finished_ids": [],
        "active_runner_trace_id": None,
    }
    start = time.perf_counter()
    original_generate = None

    class Audited:
        @property
        def metadata(self):
            trace_id = CONTEXT.get()
            meta = dict(inner.metadata)
            if trace_id and (RUN / "requests" / (trace_id + ".json")).exists():
                request = read(RUN / "requests" / (trace_id + ".json"))
                meta.update(
                    retrieval_trace_id=trace_id,
                    shared_ledger_attempt_id=request["attempt_id"],
                    actual_payload_sha256=request["payload_sha256"],
                )
            return meta

        def load(self):
            nonlocal original_generate
            try:
                check("medical")
                check_capacity("medical")
                import torch
                from transformers import set_seed

                set_seed(42)
                torch.cuda.reset_peak_memory_stats()
                inner.load()
                original_generate = inner.model.generate

                def capture(*args, **kwargs):
                    trace_id = CONTEXT.get()
                    request = read(RUN / "requests" / (trace_id + ".json"))
                    ledger.started(request["attempt_id"])
                    state["generation_attempt_ids"].append(request["attempt_id"])
                    prompt = kwargs["input_ids"][0].detach().cpu().tolist()
                    decoded = inner.tokenizer.decode(prompt, skip_special_tokens=False)
                    write(RUN / "worker-state.json", state)
                    try:
                        output = original_generate(*args, **kwargs)
                    finally:
                        state["generation_finished_ids"].append(request["attempt_id"])
                        write(RUN / "worker-state.json", state)
                    tokens = output[0, len(prompt) :].detach().cpu().tolist()
                    eos = inner.model.generation_config.eos_token_id
                    eos = eos if isinstance(eos, list) else [eos]
                    write(
                        RUN / "token-traces" / (trace_id + ".json"),
                        {
                            "trace_id": trace_id,
                            "attempt_id": request["attempt_id"],
                            "input_tokens": len(prompt),
                            "generated_tokens": len(tokens),
                            "actual_prompt_sha256": digest(decoded),
                            "actual_decoded_prompt": decoded,
                            "finish_reason": "eos"
                            if tokens and tokens[-1] in eos
                            else "length",
                            "truncated": len(tokens) >= kwargs["max_new_tokens"]
                            and (not tokens or tokens[-1] not in eos),
                        },
                    )
                    return output

                inner.model.generate = capture
                state.update(
                    status="ready",
                    metadata=inner.metadata,
                    load_seconds=time.perf_counter() - start,
                    frozen_manifest_sha256=file_hash(RUN / "experiment-manifest.json"),
                )
                write(RUN / "medical-server.json", state)
            except Exception as exc:
                state.update(status="load_failed", error_type=type(exc).__name__)
                write(RUN / "medical-server.json", state)
                raise

        def generate(self, payload):
            trace_id = CONTEXT.get()
            if not trace_id or not (RUN / "requests" / (trace_id + ".json")).exists():
                raise ServiceError("SUPPLEMENT_REQUEST_NOT_RESERVED", 403)
            request = read(RUN / "requests" / (trace_id + ".json"))
            if digest(payload) != request["payload_sha256"]:
                raise ServiceError("RETRIEVAL_PAYLOAD_HASH_MISMATCH", 422)
            verify_payload_evidence(payload, request["retrieval"])
            write(
                RUN / "server-inputs" / (trace_id + ".json"),
                {
                    "trace_id": trace_id,
                    "attempt_id": request["attempt_id"],
                    "input_payload_sha256": digest(payload),
                    "evidence_at_http_server": evidence_identities(payload["evidence"]),
                },
            )
            for name, sha in read(RUN / "experiment-manifest.json")["files"].items():
                # Source datasets/manifest/prompt/worker exact, no prompt or score repair.
                if file_hash(ROOT / name) != sha:
                    raise ServiceError("SUPPLEMENT_FROZEN_ARTIFACT_CHANGED", 409)
            state["active_runner_trace_id"] = trace_id
            try:
                result = inner.generate(payload)
                write(
                    RUN / "raw" / (trace_id + ".json"),
                    {
                        "trace_id": trace_id,
                        "attempt_id": request["attempt_id"],
                        "input_payload_sha256": digest(payload),
                        "evidence_at_http_server": evidence_identities(
                            payload["evidence"]
                        ),
                        "raw": vars(result),
                        "execution": "real_local_medical_adapter_http",
                    },
                )
                return result
            except Exception as exc:
                write(
                    RUN / "generation-errors" / (trace_id + ".json"),
                    {
                        "type": type(exc).__name__,
                        "code": getattr(exc, "code", "GENERATION_ERROR"),
                        "attempt_id": request["attempt_id"],
                    },
                )
                raise
            finally:
                state["active_runner_trace_id"] = None
                write(RUN / "worker-state.json", state)

        def close(self):
            if inner.model is not None and original_generate:
                inner.model.generate = original_generate
            try:
                import torch

                if torch.cuda.is_initialized():
                    state.update(
                        peak_vram_allocated_bytes=torch.cuda.max_memory_allocated(),
                        peak_vram_reserved_bytes=torch.cuda.max_memory_reserved(),
                    )
            except ImportError:
                pass
            inner.close()
            gc.collect()
            state.update(
                status="process_shutting_down", wall_seconds=time.perf_counter() - start
            )
            write(RUN / "medical-server.json", state)

    app = create_app(settings, Audited())
    attach_worker_state(app, state, settings.api_key)

    @app.middleware("http")
    async def trace(request, call_next):
        value = None
        try:
            value = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
        except ValueError:
            pass
        token = CONTEXT.set(value)
        try:
            return await call_next(request)
        finally:
            CONTEXT.reset(token)

    uvicorn.run(
        app, host="0.0.0.0", port=8101, workers=1, access_log=False, log_level="error"
    )


if __name__ == "__main__":
    main()
