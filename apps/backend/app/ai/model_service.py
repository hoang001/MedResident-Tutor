"""Async single-port inference client. No inference retries or provider fallback."""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.modules.practice.contracts import (
    EvaluationRequest,
    ServiceError,
    input_errors,
    strict_json,
    validate_output,
    validate_teaching,
)


class ServiceStatus(TypedDict):
    status: Literal["healthy", "ready"]


class ModelServiceError(ServiceError):
    def __init__(self, code: str, status: int, *, upstream_status=None, upstream_code=None):
        super().__init__(code, status)
        self.upstream_status = upstream_status
        self.upstream_code = upstream_code


@dataclass(frozen=True)
class InferenceResult:
    value: dict[str, Any]
    model_metadata: dict[str, Any]
    timing: dict[str, Any]


class ModelServiceClient:
    def __init__(self, settings, *, transport: httpx.AsyncBaseTransport | None = None):
        base, key = settings.model_service_base_url.strip(), settings.model_service_api_key
        if not base and settings.runpod_pod_id.strip():
            pod_id = settings.runpod_pod_id.strip()
            # One DNS label, excluding the fixed '-8000' suffix. No URLs/paths.
            if len(pod_id) > 58 or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", pod_id):
                raise ModelServiceError("MODEL_SERVICE_POD_ID_INVALID", 503)
            base = f"https://{pod_id}-8000.proxy.runpod.net"
        if (
            not base
            or not key.strip()
            or any(c in base + key for c in "<>\r\n")
            or key == "replace-me"
        ):
            raise ModelServiceError("MODEL_SERVICE_NOT_CONFIGURED", 503)
        parts = urlsplit(base)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path.rstrip("/")
        ):
            raise ModelServiceError("MODEL_SERVICE_URL_INVALID", 503)
        self.base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        self._key = key
        self._timeout = httpx.Timeout(
            connect=settings.model_service_connect_timeout_seconds,
            read=settings.model_service_read_timeout_seconds,
            write=10,
            pool=5,
        )
        self._transport = transport

    async def _request(self, method: str, path: str, payload=None, request_id=None) -> dict:
        headers = {"X-API-Key": self._key}
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                trust_env=False,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    self.base + path,
                    headers=headers,
                    **({"json": payload} if payload is not None else {}),
                )
        except httpx.ConnectTimeout:
            raise ModelServiceError("MODEL_SERVICE_UNAVAILABLE", 503) from None
        except (httpx.ReadTimeout, httpx.WriteTimeout):
            raise ModelServiceError("MODEL_SERVICE_TIMEOUT", 504) from None
        except (httpx.PoolTimeout, httpx.RequestError):
            raise ModelServiceError("MODEL_SERVICE_UNAVAILABLE", 503) from None
        if not response.is_success:
            code = {
                401: "MODEL_SERVICE_UNAUTHORIZED",
                403: "MODEL_SERVICE_UNAUTHORIZED",
                429: "MODEL_SERVICE_BUSY",
                503: "MODEL_SERVICE_NOT_READY",
                413: "MODEL_INPUT_TOO_LARGE",
                422: "MODEL_INPUT_INVALID",
                408: "MODEL_SERVICE_TIMEOUT",
                504: "MODEL_SERVICE_TIMEOUT",
                524: "MODEL_SERVICE_TIMEOUT",
            }.get(response.status_code, "MODEL_INFERENCE_FAILED")
            status = {429: 429, 503: 503, 413: 413, 422: 422, 408: 504, 504: 504, 524: 504}.get(
                response.status_code, 502
            )
            upstream_code = None
            try:
                candidate = strict_json(response.text).get("error", {}).get("code")
                if (
                    isinstance(candidate, str)
                    and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", candidate)
                    and self._key not in candidate
                ):
                    upstream_code = candidate
            except (ValueError, TypeError, AttributeError, RecursionError):
                pass
            raise ModelServiceError(
                code, status, upstream_status=response.status_code, upstream_code=upstream_code
            )
        try:
            data = strict_json(response.text)
            if not isinstance(data, dict):
                raise ValueError("Expected object")
            return data
        except (ValueError, TypeError, RecursionError):
            raise ModelServiceError("MODEL_INFERENCE_FAILED", 502) from None

    async def health(self) -> ServiceStatus:
        data = await self._request("GET", "/health")
        if data.get("status") != "healthy":
            raise ModelServiceError("MODEL_INFERENCE_FAILED", 502)
        return {"status": "healthy"}

    async def ready(self) -> ServiceStatus:
        data = await self._request("GET", "/ready")
        if data.get("status") != "ready":
            raise ModelServiceError("MODEL_SERVICE_NOT_READY", 503)
        return {"status": "ready"}

    def _result(self, data, field, validate) -> InferenceResult:
        try:
            value = validate(data[field])
            metadata, timing = data.get("model_metadata", {}), data.get("timing", {})
            if not isinstance(metadata, dict) or not isinstance(timing, dict):
                raise ValueError()
            if self._key in json.dumps(
                {"metadata": metadata, "timing": timing}, ensure_ascii=False
            ):
                raise ValueError()
            return InferenceResult(value, metadata, timing)
        except (ServiceError, ValueError, TypeError, KeyError, RecursionError):
            raise ModelServiceError("MODEL_INFERENCE_FAILED", 502) from None

    async def medical_evaluate(
        self, payload: dict, *, request_id: str | None = None
    ) -> InferenceResult:
        try:
            request = EvaluationRequest.model_validate(payload)
        except ValueError:
            raise ModelServiceError("MODEL_INPUT_INVALID", 422) from None
        data = await self._request("POST", "/medical/evaluate", payload, request_id)
        return self._result(
            data,
            "medical_evaluation",
            lambda value: validate_output(json.dumps(value, allow_nan=False), request),
        )

    async def teaching_feedback(
        self, payload: dict, *, request_id: str | None = None
    ) -> InferenceResult:
        try:
            if input_errors(payload):
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ModelServiceError("MODEL_INPUT_INVALID", 422) from None
        data = await self._request("POST", "/teaching/feedback", payload, request_id)
        return self._result(
            data, "teaching_feedback", lambda value: validate_teaching(payload, value)
        )
