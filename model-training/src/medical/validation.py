import json
import math

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError, model_validator
from src.medical.inference import extract_json


class ServiceError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("Nonfinite JSON constant")

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)

    # 1e999 is valid JSON syntax but produces infinity in Python.
    def finite(obj):
        if isinstance(obj, float) and not math.isfinite(obj):
            raise ValueError("Nonfinite number")
        if isinstance(obj, dict):
            for v in obj.values():
                finite(v)
        elif isinstance(obj, list):
            for v in obj:
                finite(v)

    finite(value)
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Criterion(StrictModel):
    model_config = ConfigDict(strict=True, extra="allow")
    criterion_id: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    max_score: FiniteFloat = Field(gt=0)
    required_source_unit_ids: list[str]


class Rubric(StrictModel):
    model_config = ConfigDict(strict=True, extra="allow")
    rubric_id: str = Field(min_length=1)
    max_score: FiniteFloat = Field(gt=0)
    criteria: list[Criterion] = Field(min_length=1, max_length=100)


class Evidence(StrictModel):
    model_config = ConfigDict(strict=True, extra="allow")
    source_unit_id: str = Field(min_length=1, max_length=255)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    content: str = Field(min_length=1)


class EvaluationRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    student_answer: str = Field(min_length=1, max_length=16000)
    rubric: Rubric
    evidence: list[Evidence] = Field(max_length=100)

    @model_validator(mode="after")
    def references(self):
        ids = [c.criterion_id for c in self.rubric.criteria]
        refs = [e.source_unit_id for e in self.evidence]
        if len(ids) != len(set(ids)) or len(refs) != len(set(refs)):
            raise ValueError("Duplicate request IDs")
        if not self.question.strip() or not self.student_answer.strip():
            raise ValueError("Empty input")
        if any(e.page_end < e.page_start or not e.content.strip() for e in self.evidence):
            raise ValueError("Invalid evidence")
        if any(
            len(c.required_source_unit_ids) != len(set(c.required_source_unit_ids))
            for c in self.rubric.criteria
        ):
            raise ValueError("Duplicate required_source_unit_ids")
        if not close(sum(c.max_score for c in self.rubric.criteria), self.rubric.max_score):
            raise ValueError("Rubric total mismatch")
        return self


class RubricScore(StrictModel):
    criterion_id: str = Field(min_length=1)
    criterion: str = Field(min_length=1)
    score: FiniteFloat
    max_score: FiniteFloat
    reason: str = Field(min_length=1)


class MedicalEvaluation(StrictModel):
    correct_points: list[str]
    incorrect_points: list[str]
    missing_points: list[str]
    rubric_scores: list[RubricScore]
    total_score: FiniteFloat
    max_score: FiniteFloat
    sufficient_evidence: bool
    evidence_refs: list[str]


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-9)


def validate_input(raw: bytes) -> tuple[dict, EvaluationRequest]:
    try:
        payload = strict_json(raw.decode("utf-8"))
        request = EvaluationRequest.model_validate(payload)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ServiceError("INVALID_REQUEST", 422) from None
    return payload, request


def validate_output(raw: str, request: EvaluationRequest) -> dict:
    if not isinstance(raw, str):
        raise ServiceError("MODEL_OUTPUT_INVALID_JSON", 502)
    try:
        # Same fence/prose extraction as pilot, with stricter JSON decoding.
        prediction, error = extract_json(raw, loads=strict_json)
        if error or prediction is None:
            raise ValueError("Invalid JSON")
    except (ValueError, TypeError, RecursionError):
        raise ServiceError("MODEL_OUTPUT_INVALID_JSON", 502) from None
    try:
        output = MedicalEvaluation.model_validate(prediction)
    except ValidationError:
        raise ServiceError("MODEL_OUTPUT_INVALID_SCHEMA", 502) from None
    criteria = request.rubric.criteria
    ids = [s.criterion_id for s in output.rubric_scores]
    if ids != [c.criterion_id for c in criteria]:
        raise ServiceError("MODEL_OUTPUT_CRITERION_MISMATCH", 502)
    for score, criterion in zip(output.rubric_scores, criteria, strict=True):
        if (
            not close(score.max_score, criterion.max_score)
            or not 0 <= score.score <= criterion.max_score
        ):
            raise ServiceError("MODEL_OUTPUT_SCORE_INVALID", 502)
    if (
        not close(output.max_score, request.rubric.max_score)
        or not close(output.total_score, sum(s.score for s in output.rubric_scores))
        or not 0 <= output.total_score <= request.rubric.max_score
    ):
        raise ServiceError("MODEL_OUTPUT_TOTAL_MISMATCH", 502)
    refs = output.evidence_refs
    if len(refs) != len(set(refs)) or not set(refs) <= {e.source_unit_id for e in request.evidence}:
        raise ServiceError("MODEL_OUTPUT_EVIDENCE_INVALID", 502)
    # Return original values, never repair/round/rewrite model output.
    return prediction
