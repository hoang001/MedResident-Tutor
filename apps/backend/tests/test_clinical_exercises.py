"""Authored-exercise adapter and no-gold projections, without model calls."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.integration.clinical_cases import load_bundle
from app.integration.inputs import CaseError, digest
from app.modules.practice.assets import image_response, learner_view
from app.modules.practice.service import view

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "data/clinical-cases/exercises"


def authored():
    image = {"asset_id": "a" * 24, "width": 10, "height": 20}
    return {
        "learner": {
            "title": "Neutral title",
            "presentation": "History",
            "question": "Task",
            "notice": "Review required",
            "images": [image],
            "rubric": "must not leak",
        },
        "criteria": [
            {
                "criterion_id": "C",
                "description": "Criterion",
                "max_score": 1.0,
                "reference_answer_vi": "Private answer",
                "acceptable_variants": [],
            }
        ],
        "answer_annotations": [{"asset_id": "a" * 24, "box": {"xmin": 1}}],
        "source": {
            "title": "Answer-bearing title",
            "original_url": "https://example.com",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution_text": "Author",
        },
    }


def test_learner_projection_ignores_all_private_and_unexpected_fields():
    result = learner_view(authored(), "/practice/questions/Q")
    assert "Private answer" not in json.dumps(result)
    assert "Answer-bearing title" not in json.dumps(result)
    assert "rubric" not in result and "annotations" not in result
    assert result["images"][0]["alt"] == "Ảnh 1 của bài tập"
    assert result["images"][0]["url"] == "/practice/questions/Q/assets/" + "a" * 24


def test_pending_attempt_does_not_expose_solution_but_completed_medical_does():
    row = SimpleNamespace(
        id="A",
        snapshot={
            "payload": {"rubric": {"question_id": "Q"}, "question": "Task", "evidence": []},
            "provenance": [],
            "hash": "h",
            "clinical_exercise": authored(),
        },
        student_answer="The student's actual answer",
        status="pending",
        execution_mode="mock",
        medical_evaluation=None,
        teaching_feedback=None,
        provider_metadata={},
        stage_error=None,
        created_at=datetime.now(UTC),
    )
    result = view(row)
    assert "clinical_solution" not in result
    assert "Private answer" not in json.dumps(result)
    assert result["student_answer"] == "The student's actual answer"
    row.medical_evaluation = {"total_score": 0}
    row.status = "teaching_running"
    assert view(row)["clinical_solution"]["criteria"][0]["reference_answer_vi"] == "Private answer"


@pytest.mark.parametrize("identifier", ["../secret", "original-figure-f1", "", "b" * 24])
async def test_image_rejects_unknown_or_answer_bearing_identifiers(tmp_path, identifier):
    data = authored()
    data["assets"] = []
    with pytest.raises(HTTPException) as error:
        await image_response(data, identifier, tmp_path)
    assert error.value.status_code == 404


async def test_image_file_is_private_neutral_and_hash_guarded(tmp_path):
    image_id = "a" * 24
    path = tmp_path / "clinical-exercises" / (image_id + ".png")
    path.parent.mkdir()
    path.write_bytes(b"original image bytes")
    data = {
        "assets": [
            {
                "asset_id": image_id,
                "storage_key": "clinical-exercises/" + path.name,
                "sha256": digest(path),
                "mime_type": "image/png",
            }
        ]
    }
    response = await image_response(data, image_id, tmp_path)
    assert response.headers["cache-control"] == "private, no-store"
    assert "image-" + image_id in response.headers["content-disposition"]
    path.write_bytes(b"modified")
    with pytest.raises(HTTPException):
        await image_response(data, image_id, tmp_path)


@pytest.mark.skipif(not (BUNDLE / "assets").exists(), reason="Local licensed assets not bundled")
def test_real_two_demo_adapter_uses_real_packets_no_invented_course_or_topic():
    rows = load_bundle(BUNDLE)
    assert len(rows) == 2
    for case, data in rows:
        assert case.rubric["course_id"] is None and case.rubric["topic_id"] is None
        assert case.manifest["expert_review"]["status"] == "unverified"
        assert data["packet_page_basis"] == "compiled_packet_not_original_article"
        assert sum(c["max_score"] for c in case.rubric["criteria"]) == 2
        assert case.pdf.read_bytes().startswith(b"%PDF-")


def test_bundle_refuses_unreviewed_demo_ids(tmp_path):
    manifest = {"demo_ids": ["UNREVIEWED"], "rows": []}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(CaseError, match="two reviewed"):
        load_bundle(tmp_path)


def test_original_learner_projection_does_not_mutate_private_metadata():
    data = authored()
    original = copy.deepcopy(data)
    learner_view(data, "/x")
    assert data == original
