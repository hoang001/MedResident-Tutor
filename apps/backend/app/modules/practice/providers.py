"""Replaceable async providers. No fallback and no content/secrets logging."""

import re
import uuid

import httpx

from app.modules.practice.contracts import ServiceError, strict_json


class MockProvider:
    mode = "mock"

    def __init__(self, scenario="success"):
        if scenario not in {
            "success",
            "medical_error",
            "medical_invalid",
            "teaching_error",
            "teaching_invalid",
            "timeout",
            "busy",
        }:
            raise ValueError("Unknown practice mock scenario")
        self.scenario = scenario
        self.calls = {"medical": 0, "teaching": 0}

    async def evaluate(self, stage, payload, retry=False):
        self.calls[stage] += 1
        if self.scenario == "busy":
            raise ServiceError("PROVIDER_BUSY", 429)
        if self.scenario == "timeout":
            raise ServiceError("PROVIDER_TIMEOUT", 504)
        if self.scenario == stage + "_error" and not retry:
            raise ServiceError("PROVIDER_FAILED", 502)
        if stage == "medical":
            rubric = payload["rubric"]
            result = dict(
                correct_points=[],
                incorrect_points=[],
                missing_points=[c["description"] for c in rubric["criteria"]],
                rubric_scores=[
                    dict(
                        criterion_id=c["criterion_id"],
                        criterion=c["description"],
                        score=0.0,
                        max_score=c["max_score"],
                        reason="Fixed development fixture; answer is not graded.",
                    )
                    for c in rubric["criteria"]
                ],
                total_score=0.0,
                max_score=rubric["max_score"],
                sufficient_evidence=True,
                evidence_refs=[e["source_unit_id"] for e in payload["evidence"]],
            )
            if self.scenario == "medical_invalid":
                result["total_score"] = 99999
        else:
            med = payload["medical_evaluation"]
            result = dict(
                strengths=list(med["correct_points"]),
                corrections=[dict(incorrect_point=x, feedback=x) for x in med["incorrect_points"]],
                missing_focus=[dict(missing_point=x, feedback=x) for x in med["missing_points"]],
                learning_priority=[
                    dict(focus=x, priority="high", reason="Mock fixture priority.")
                    for x in med["incorrect_points"] + med["missing_points"]
                ],
                feedback_text="Mock feedback for testing data flow only.",
                follow_up_question=None,
            )
            if self.scenario == "teaching_invalid":
                result["missing_focus"] = []
        return result, {
            "provider": "deterministic-fixture-v1",
            "invocation_id": str(uuid.uuid4()),
            "execution_mode": "mock",
            "scenario": self.scenario,
        }


class HTTPProvider:
    mode = "http"

    def __init__(self, settings, stages=("medical", "teaching"), request_id=None):
        self.settings = settings
        self.request_id = str(uuid.UUID(request_id)) if request_id else None
        self.stages = frozenset(stages)
        if not self.stages or not self.stages <= {"medical", "teaching"}:
            raise ValueError("Unknown HTTP practice stage")
        if not all(
            getattr(settings, stage + "_service_url")
            and getattr(settings, stage + "_service_api_key")
            for stage in self.stages
        ):
            raise ServiceError("HTTP_PROVIDER_NOT_CONFIGURED", 503)
        from app.ai.remote_chat import configured

        for stage in self.stages:
            if not all(
                configured(getattr(settings, stage + suffix))
                for suffix in ("_service_url", "_service_api_key")
            ):
                raise ServiceError("HTTP_PROVIDER_NOT_CONFIGURED", 503)
            if getattr(settings, stage + "_api_format") == "openai" and not configured(
                getattr(settings, stage + "_model")
            ):
                raise ServiceError("HTTP_PROVIDER_NOT_CONFIGURED", 503)

    async def evaluate(self, stage, payload, retry=False):
        if stage not in self.stages:
            raise ServiceError("HTTP_STAGE_NOT_CONFIGURED", 503)
        if getattr(self.settings, stage + "_api_format") == "openai":
            from app.ai.remote_chat import chat, grading_messages

            request_id = self.request_id or str(uuid.uuid4())
            result, metadata = await chat(
                base=getattr(self.settings, stage + "_service_url"),
                key=getattr(self.settings, stage + "_service_api_key"),
                model=getattr(self.settings, stage + "_model"),
                messages=grading_messages(stage, payload),
                max_tokens=1200 if stage == "medical" else 1600,
                timeout=httpx.Timeout(**self.settings.practice_transport_timeouts(stage)),
                request_id=request_id,
            )
            return result, {
                "execution_mode": "http",
                "request_id": request_id,
                "model_metadata": metadata,
            }
        url = getattr(self.settings, stage + "_service_url").rstrip("/") + "/" + stage + "/evaluate"
        key = getattr(self.settings, stage + "_service_api_key")
        request_id = self.request_id or str(uuid.uuid4())
        try:
            timeout = httpx.Timeout(**self.settings.practice_transport_timeouts(stage))
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                response = await client.post(
                    url, json=payload, headers={"X-API-Key": key, "X-Request-ID": request_id}
                )
            if response.status_code == 429:
                raise ServiceError("PROVIDER_BUSY", 429)
            if not response.is_success:
                try:
                    code = response.json().get("error", {}).get("code", "")
                except (ValueError, AttributeError):
                    code = ""
                if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code):
                    code = "PROVIDER_FAILED"
                raise ServiceError(code, response.status_code)
            data = strict_json(response.text)
            result = data["medical_evaluation" if stage == "medical" else "teaching_feedback"]
            metadata = data.get("model_metadata", {})
            return result, {
                "execution_mode": "http",
                "request_id": request_id,
                "model_metadata": metadata,
                "timing": data.get("timing", {}),
            }
        except (TimeoutError, httpx.TimeoutException):
            raise ServiceError("PROVIDER_TIMEOUT", 504) from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ServiceError("PROVIDER_RESPONSE_INVALID", 502) from None

    def set_retrieval_context(self, trace):
        self.request_id = str(uuid.UUID(trace["trace_id"]))


def get_provider(settings):
    if settings.practice_provider != "mock" and not settings.model_calls_enabled:
        raise ServiceError("MODEL_CALLS_DISABLED", 503)
    if settings.practice_provider == "mock":
        if settings.app_env != "development":
            raise ServiceError("MOCK_FORBIDDEN", 503)
        return MockProvider(settings.practice_mock_scenario)
    if settings.practice_provider == "http":
        return HTTPProvider(settings)
    raise ServiceError("UNKNOWN_PROVIDER", 503)
