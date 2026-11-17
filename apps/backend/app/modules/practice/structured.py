"""Small, source-authored exercise contract. No inference, text matching or mastery writes."""

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Option(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=500)


class Focus(StrictModel):
    label: str
    concept_id: str | None = None  # Only an already verified link, never inferred from a title.


class Part(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["single_choice", "grid_location", "short_explanation"]
    label: str
    max_score: int = Field(ge=0, le=10)
    options: list[Option] = Field(default_factory=list, max_length=12)
    correct_option_id: str | None = None
    criterion_id: str | None = None
    explanation: str = ""
    correct_feedback: str = ""
    incorrect_feedback: dict[str, str] = Field(default_factory=dict)
    unanswered_feedback: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    review_focus: list[Focus] = Field(default_factory=list)
    asset_id: str | None = None
    max_length: int = Field(default=4000, ge=1, le=4000)

    @model_validator(mode="after")
    def check(self):
        ids = [o.id for o in self.options]
        if self.kind == "short_explanation":
            if self.max_score or ids or self.correct_option_id or self.criterion_id:
                raise ValueError("Explanation must be unscored")
            return self
        if (
            len(ids) < 2
            or len(set(ids)) != len(ids)
            or self.correct_option_id not in ids
            or not self.criterion_id
            or self.max_score <= 0
            or not self.evidence_ids
            or not self.explanation
            or not self.correct_feedback
            or not self.unanswered_feedback
            or set(self.incorrect_feedback) != set(ids) - {self.correct_option_id}
            or not all(self.incorrect_feedback.values())
        ):
            raise ValueError("Incomplete scored part/feedback/evidence")
        if self.kind == "grid_location" and (
            set(ids) != {f"r{r}c{c}" for r in range(1, 4) for c in range(1, 4)} or not self.asset_id
        ):
            raise ValueError("Grid must use r1c1..r3c3 and a target image")
        return self


class Exercise(StrictModel):
    schema_version: Literal["structured-v1"]
    revision_id: str
    legacy_question_id: str
    review_status: Literal["source_checked_expert_review_pending"]
    scoring_policy: Literal["independent_exact_id_fixed_denominator"]
    parts: list[Part] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def check(self):
        ids = [p.id for p in self.parts]
        criteria = [p.criterion_id for p in self.parts if p.max_score]
        if len(ids) != len(set(ids)) or not criteria or len(criteria) != len(set(criteria)):
            raise ValueError("Duplicate/missing part or criterion IDs")
        if sum(p.kind == "short_explanation" for p in self.parts) > 1:
            raise ValueError("Only one optional explanation is supported")
        return self


def definition(metadata):
    raw = (metadata or {}).get("dataset_fields", {}).get("structured_exercise")
    return Exercise.model_validate(raw) if raw is not None else None


def learner_view(exercise):
    """Explicit allowlist: no answer key, feedback, evidence, mappings or source titles."""
    return {
        "schema_version": exercise.schema_version,
        "revision_id": exercise.revision_id,
        "max_score": sum(p.max_score for p in exercise.parts),
        "scoring_policy": exercise.scoring_policy,
        "parts": [
            {
                "id": p.id,
                "kind": p.kind,
                "label": p.label,
                "max_score": p.max_score,
                "options": [o.model_dump() for o in p.options],
                **(
                    {
                        "asset_id": p.asset_id,
                        "grid_size": 3,
                        "coordinates": "rows_top_to_bottom_columns_left_to_right_1_based",
                    }
                    if p.kind == "grid_location"
                    else {}
                ),
                **({"max_length": p.max_length} if p.kind == "short_explanation" else {}),
            }
            for p in exercise.parts
        ],
    }


def grade(exercise, answers):
    if not isinstance(answers, dict) or set(answers) - {p.id for p in exercise.parts}:
        raise HTTPException(422, "Unknown structured field ID")
    parts = []
    for p in exercise.parts:
        value = answers.get(p.id)
        if p.kind == "short_explanation":
            if value is not None and (not isinstance(value, str) or len(value) > p.max_length):
                raise HTTPException(422, "Invalid short explanation")
            parts.append(
                {
                    "id": p.id,
                    "label": p.label,
                    "kind": p.kind,
                    "status": "unscored",
                    "answer": value,
                    "score": 0,
                    "max_score": 0,
                }
            )
            continue
        labels = {o.id: o.label for o in p.options}
        if value is not None and (not isinstance(value, str) or value not in labels):
            raise HTTPException(422, "Unknown option/grid ID for " + p.id)
        status = (
            "unanswered"
            if value is None
            else "correct"
            if value == p.correct_option_id
            else "incorrect"
        )
        feedback = (
            p.unanswered_feedback
            if status == "unanswered"
            else p.correct_feedback
            if status == "correct"
            else p.incorrect_feedback[value]
        )
        parts.append(
            {
                "id": p.id,
                "kind": p.kind,
                "label": p.label,
                "criterion_id": p.criterion_id,
                "status": status,
                "answer": value,
                "answer_label": labels.get(value),
                "score": p.max_score if status == "correct" else 0,
                "max_score": p.max_score,
                "correct_option_id": p.correct_option_id,
                "correct_answer": labels[p.correct_option_id],
                "feedback": feedback,
                "explanation": p.explanation,
                "evidence_ids": p.evidence_ids,
                "review_focus": [f.model_dump() for f in p.review_focus],
            }
        )
    return {
        "revision_id": exercise.revision_id,
        "schema_version": exercise.schema_version,
        "total_score": sum(p["score"] for p in parts),
        "max_score": sum(p["max_score"] for p in parts),
        "parts": parts,
    }
