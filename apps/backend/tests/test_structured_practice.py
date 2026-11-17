import copy
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.integration.clinical_cases import load_bundle
from app.modules.practice.structured import Exercise, grade, learner_view

BUNDLE = Path(__file__).resolve().parents[3] / "data/clinical-cases/exercises"


@pytest.fixture(params=["CASE01", "XR01"])
def exercise(request):
    path = BUNDLE / "structured" / ("CLINICAL_DEMO_V2_" + request.param + ".json")
    return Exercise.model_validate(json.loads(path.read_text(encoding="utf-8")))


def correct(exercise):
    return {p.id: p.correct_option_id for p in exercise.parts if p.max_score}


def test_score_states_and_unscored_explanation(exercise):
    answers = correct(exercise)
    assert grade(exercise, answers)["total_score"] == 2
    first = exercise.parts[0]
    answers[first.id] = next(o.id for o in first.options if o.id != first.correct_option_id)
    partial = grade(exercise, answers)
    assert partial["total_score"] == 1
    assert partial["parts"][0]["status"] == "incorrect"
    for p in exercise.parts:
        if p.max_score:
            answers[p.id] = next(o.id for o in p.options if o.id != p.correct_option_id)
    wrong = grade(exercise, answers)
    assert wrong["total_score"] == 0
    empty = grade(exercise, {})
    assert empty["max_score"] == 2 and empty["total_score"] == 0
    assert [p["status"] for p in empty["parts"]] == ["unanswered", "unanswered", "unscored"]
    assert empty["parts"][0]["feedback"] != wrong["parts"][0]["feedback"]
    text = "  A free explanation contradicting every selected option.\n "
    with_text = grade(exercise, {**answers, "explanation": text})
    assert with_text["total_score"] == wrong["total_score"]
    assert with_text["parts"][-1]["answer"] == text


@pytest.mark.parametrize(
    "invalid",
    [
        {"unknown": "o1"},
        {"part_1": "unknown"},
        {"part_2": "r0c0"},
        {"part_1": True},
        {"part_1": ["o1"]},
        {"explanation": "x" * 4001},
    ],
)
def test_reject_foreign_or_wrongly_typed_answers(exercise, invalid):
    with pytest.raises(HTTPException) as exc:
        grade(exercise, invalid)
    assert exc.value.status_code == 422


def test_pre_submission_projection_is_allowlist(exercise):
    data = learner_view(exercise)
    encoded = json.dumps(data)
    for field in (
        "correct_option_id",
        "criterion_id",
        "feedback",
        "evidence_ids",
        "review_focus",
        "explanation",
        "concept_id",
    ):
        # The explanation input ID is allowed, the private explanation key is not.
        assert '"' + field + '":' not in encoded
    assert data["max_score"] == 2


def test_definition_requires_feedback_for_every_wrong_option(exercise):
    raw = exercise.model_dump()
    raw["parts"][0]["incorrect_feedback"] = {}
    with pytest.raises(ValidationError):
        Exercise.model_validate(raw)


def test_structured_import_is_new_identity_without_mutating_v1():
    old = load_bundle(BUNDLE)
    frozen = copy.deepcopy(old)
    new = load_bundle(BUNDLE, structured=True)
    assert old == frozen
    for (case, authored), (legacy, _) in zip(new, old, strict=True):
        assert case.question["question_id"] == legacy.question["question_id"].replace(
            "_V1_", "_V2_"
        )
        assert case.sha256 == legacy.sha256
        assert authored["assets"] == legacy.manifest["clinical_exercise"]["assets"]
        exercise = Exercise.model_validate(case.question["structured_exercise"])
        assert grade(exercise, correct(exercise))["max_score"] == case.rubric["max_score"]


def test_ten_authored_definitions_bind_existing_sources_and_concepts_only():
    manifest = json.loads((BUNDLE / "structured/manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["rows"]) == 10
    assert sum(r["status"] == "demo" for r in manifest["rows"]) == 2
    for row in manifest["rows"]:
        exercise = Exercise.model_validate(
            json.loads(
                (BUNDLE / "structured" / (row["question_id"] + ".json")).read_text(encoding="utf-8")
            )
        )
        grading = json.loads(
            (BUNDLE / "grading" / (row["legacy_question_id"] + ".json")).read_text(encoding="utf-8")
        )
        criteria = {c["criterion_id"].replace("_V1_", "_V2_"): c for c in grading["criteria"]}
        assert grade(exercise, correct(exercise))["total_score"] == grading["max_score"]
        for p in exercise.parts:
            if not p.max_score:
                continue
            c = criteria[p.criterion_id]
            assert p.evidence_ids == [
                s.replace("_V1_", "_V2_") for s in c["required_source_unit_ids"]
            ]
            assert {f.concept_id for f in p.review_focus if f.concept_id} <= {
                link["id"] for link in c["kg_links"]
            }
        if row["question_id"].endswith("XR01"):
            grid = next(p for p in exercise.parts if p.kind == "grid_location")
            assert grid.correct_option_id == "r2c2"
            assert grid.asset_id == grading["answer_annotations"][0]["asset_id"]
