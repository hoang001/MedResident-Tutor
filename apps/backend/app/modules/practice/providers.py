"""Replaceable async providers. No fallback and no content/secrets logging."""

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

    def __init__(self, settings):
        self.settings = settings
        if not all(
            (
                settings.medical_service_url,
                settings.teaching_service_url,
                settings.medical_service_api_key,
                settings.teaching_service_api_key,
            )
        ):
            raise ServiceError("HTTP_PROVIDER_NOT_CONFIGURED", 503)

    async def evaluate(self, stage, payload, retry=False):
        url = getattr(self.settings, stage + "_service_url").rstrip("/") + "/" + stage + "/evaluate"
        key = getattr(self.settings, stage + "_service_api_key")
        try:
            async with httpx.AsyncClient(timeout=self.settings.practice_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers={"X-API-Key": key})
            if response.status_code == 429:
                raise ServiceError("PROVIDER_BUSY", 429)
            if not response.is_success:
                raise ServiceError("PROVIDER_FAILED", 502)
            data = strict_json(response.text)
            result = data["medical_evaluation" if stage == "medical" else "teaching_feedback"]
            metadata = data.get("model_metadata", {})
            return result, {
                "execution_mode": "http",
                "model_metadata": metadata,
                "timing": data.get("timing", {}),
            }
        except (TimeoutError, httpx.TimeoutException):
            raise ServiceError("PROVIDER_TIMEOUT", 504) from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ServiceError("PROVIDER_RESPONSE_INVALID", 502) from None


def get_provider(settings):
    if settings.practice_provider == "mock":
        if settings.app_env != "development":
            raise ServiceError("MOCK_FORBIDDEN", 503)
        return MockProvider(settings.practice_mock_scenario)
    if settings.practice_provider == "http":
        return HTTPProvider(settings)
    raise ServiceError("UNKNOWN_PROVIDER", 503)
