"""Freeze new integration inputs/expected verdicts; never reads a locked test set."""

import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from .common import ROOT, REPORT, file_hash, read, write

sys.path.insert(0, str(ROOT / "model-training"))
from src.medical.validation import EvaluationRequest

BUNDLE = ROOT / "data/clinical-cases/exercises"
ANSWERS = {
    "CASE01": [
        "Gãy đầu dưới xương quay trái, gãy phạm khớp.",
        "Gãy đầu dưới xương quay trái.",
        "Gãy đầu dưới xương trụ, không phạm khớp.",
        "",
        "Tôi thích nghe nhạc vào cuối tuần.",
    ],
    "XR01": [
        "Có gãy xương; tâm vùng tổn thương ở hàng 2, cột 2.",
        "Có gãy xương.",
        "Không có gãy xương; vùng ở hàng 1, cột 1.",
        "",
        "Tôi thích nghe nhạc vào cuối tuần.",
    ],
}
LABELS = ("full", "partial", "incorrect", "empty", "unrelated")


def prepare():
    destination = REPORT / "integration-inputs.json"
    if destination.exists():
        raise ValueError(
            "Frozen inputs already exist; do not overwrite after inference"
        )
    cases, reviews = [], []
    for suffix, answers in ANSWERS.items():
        qid = "CLINICAL_DEMO_V1_" + suffix
        grading = read(BUNDLE / "grading" / (qid + ".json"))
        learner = read(BUNDLE / "learner" / (qid + ".vi.json"))
        assert (
            grading["max_score"]
            == sum(c["max_score"] for c in grading["criteria"])
            == 2
        )
        assert all(c["max_score"] == 1 for c in grading["criteria"])
        refs = {e["source_unit_id"] for e in grading["evidence"]}
        assert all(
            set(c["required_source_unit_ids"]) <= refs for c in grading["criteria"]
        )
        assert len(grading["assets"]) == len(learner["images"])
        for asset, visible in zip(grading["assets"], learner["images"], strict=True):
            assert asset["asset_id"] == visible["asset_id"]
            assert file_hash(BUNDLE / asset["bundle_path"]) == asset["sha256"]
        assert (
            file_hash(BUNDLE / grading["packet"]["path"]) == grading["packet"]["sha256"]
        )
        if suffix == "CASE01":
            original = ROOT / "data/clinical-cases/raw/pmc/PMC10182394.xml"
            assert all(
                file_hash(original) == e["source_ref"]["xml_sha256"]
                for e in grading["evidence"]
            )
            element = ET.parse(original).getroot().find("body/sec[2]/p[1]")
            assert element is not None
            text = " ".join("".join(element.itertext()).split())
            assert all(e["content_en"] == text for e in grading["evidence"])
        if suffix == "XR01":
            ref = grading["evidence"][0]["source_ref"]
            annotation = ROOT / "data/clinical-cases" / ref["annotation_path"]
            assert file_hash(annotation) == ref["annotation_sha256"]
            tree = ET.parse(annotation)
            boxes = [
                {
                    k: int(obj.findtext("bndbox/" + k))
                    for k in ("xmin", "ymin", "xmax", "ymax")
                }
                for obj in tree.findall("object")
                if obj.findtext("name", "").strip() == "fracture"
            ]
            box = ref["bbox_original"]
            assert box in boxes
            width, height = (
                grading["assets"][0]["width"],
                grading["assets"][0]["height"],
            )
            assert int((box["xmin"] + box["xmax"]) / 2 / width * 3) + 1 == 2
            assert int((box["ymin"] + box["ymax"]) / 2 / height * 3) + 1 == 2
            assert grading["assets"][0]["source_image_id"] == ref["original_image_id"]
        criteria = [
            {
                k: c[k]
                for k in (
                    "criterion_id",
                    "description",
                    "max_score",
                    "acceptable_variants",
                    "common_incorrect_claims",
                    "required_source_unit_ids",
                )
            }
            for c in grading["criteria"]
        ]
        rubric = {
            "schema_version": "1.0.0",
            "rubric_id": qid + "_R",
            "question_id": qid,
            "max_score": grading["max_score"],
            "course_id": None,
            "topic_id": None,
            "scoring_rule": "sum_of_independent_criteria_no_penalty_for_unasked_items",
            "validation_status": "source_checked_development_only",
            "expert_review_required": True,
            "expert_review_reason": "Authored exercise; source checking is not clinical expert approval",
            "criteria": criteria,
        }
        evidence = [
            {
                "source_unit_id": e["source_unit_id"],
                "source_id": "SRC_" + qid + "_PACKET",
                "title": "Evidence for " + e["source_unit_id"],
                "page_start": 1,
                "page_end": grading["packet"]["pages"],
                "content": e["content_en"],
            }
            for e in grading["evidence"]
        ]
        for label, answer in zip(LABELS, answers, strict=True):
            case_id = qid + "__" + label
            payload = {
                "question": learner["presentation"] + "\n\n" + learner["question"],
                "student_answer": answer,
                "rubric": rubric,
                "evidence": evidence,
            }
            if label != "empty":
                EvaluationRequest.model_validate(payload)
            scores = {
                "full": [1, 1],
                "partial": [1, 0],
                "incorrect": [0, 0],
                "unrelated": [0, 0],
            }.get(label)
            expected = {
                "app_http": 422 if label == "empty" else None,
                "model_call": label != "empty",
                "sufficient_evidence": True if label != "empty" else None,
                "criteria": [
                    {
                        "criterion_id": c["criterion_id"],
                        "score": scores[i],
                        "verdict": "met" if scores[i] else "not_met",
                        "evidence_refs": c["required_source_unit_ids"],
                    }
                    for i, c in enumerate(criteria)
                ]
                if scores
                else [],
                "total_score": sum(scores) if scores else None,
                "point_policy": {
                    "full": "both correct; no missing or incorrect",
                    "partial": "criterion 1 correct; criterion 2 missing, not incorrect",
                    "incorrect": "both explicitly contradicted; report incorrect claims",
                    "empty": "application rejects without provider/model invocation",
                    "unrelated": "both criteria missing; no invented clinical incorrect claim",
                }[label],
                "reason": "Two binary 1-point criteria. Source excerpt or annotation supports each; no partial points defined.",
            }
            # Expected judgements are in a separate file, never in the model request.
            write(REPORT / "inputs" / (case_id + ".json"), payload)
            write(REPORT / "expected" / (case_id + ".json"), expected)
            cases.append(
                {
                    "case_id": case_id,
                    "question_id": qid,
                    "label": label,
                    "input_sha256": file_hash(REPORT / "inputs" / (case_id + ".json")),
                    "expected_sha256": file_hash(
                        REPORT / "expected" / (case_id + ".json")
                    ),
                }
            )
        reviews.append(
            {
                "question_id": qid,
                "grading_sha256": file_hash(BUNDLE / "grading" / (qid + ".json")),
                "learner_sha256": file_hash(BUNDLE / "learner" / (qid + ".vi.json")),
                "total_checked": True,
                "assets_and_packet_hashes_checked": True,
                "source_review": "original CASE01 XML/excerpt verified; XR01 original annotation/grid recomputed",
                "expert_approved": False,
                "image_input_to_medical": False,
            }
        )
    write(
        destination,
        {
            "frozen_at": datetime.now(UTC).isoformat(),
            "cases": cases,
            "reviews": reviews,
            "locked_dataset_used": False,
            "expected_before_inference": True,
            "scope": "10 new integration scenarios; 8 model inputs + 2 app-level blank rejections",
        },
    )
    print(
        "Prepared 10 new scenarios; 8 nonempty model inputs and 2 app rejection checks. No inference."
    )


if __name__ == "__main__":
    prepare()
