"""Development-only adapter reusing the existing importer; no model/schema/KG writes.

python -m app.integration.clinical_cases --bundle /app/data/clinical-cases/exercises
Add --apply only after the host has backed up the local development database.
"""

import argparse
import asyncio
import copy
import json
from dataclasses import replace
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.common.enums import UserRole
from app.core.config import get_settings
from app.core.database import engine
from app.integration.importer import IMPORT_LOCK, persist_case
from app.integration.inputs import CaseInput, canonical_digest, digest, require, within
from app.integration.schema import assert_current_schema
from app.integration.storage import publish_pdf
from app.modules.practice.contracts import EvaluationRequest
from app.modules.practice.structured import Exercise
from app.modules.users.models import User
from app.storage.local import LocalFileStorage

DEMO_IDS = {"CLINICAL_DEMO_V1_CASE01", "CLINICAL_DEMO_V1_XR01"}


def structured_revision(case, authored, bundle):
    """New identities, same verified source bytes. Old question/attempts stay untouched."""
    old = case.question["question_id"]
    new = old.replace("_V1_", "_V2_")
    exercise = Exercise.model_validate(
        json.loads((bundle / "structured" / (new + ".json")).read_text(encoding="utf-8"))
    )
    require(
        exercise.revision_id == new and exercise.legacy_question_id == old,
        "Structured revision identity mismatch",
    )

    def remap(value):
        if isinstance(value, str):
            return value.replace(old, new)
        if isinstance(value, list):
            return [remap(x) for x in value]
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}
        return value

    case = copy.deepcopy(case)
    authored = copy.deepcopy(authored)
    case = replace(
        case, question=remap(case.question), rubric=remap(case.rubric), units=remap(case.units)
    )
    case.catalog["source_id"] = remap(case.catalog["source_id"])
    case.catalog["title"] = remap(case.catalog["title"])
    case.manifest["locator"]["section"] = new
    authored["criteria"] = remap(authored["criteria"])
    authored["learner"]["exercise_id"] = new
    authored["learner"]["title"] += " · bài có cấu trúc"
    case.manifest["clinical_exercise"] = authored
    case.question["structured_exercise"] = exercise.model_dump()
    criteria = {c["criterion_id"]: c for c in case.rubric["criteria"]}
    scored = [p for p in exercise.parts if p.max_score]
    require(set(criteria) == {p.criterion_id for p in scored}, "Structured rubric mismatch")
    for p in scored:
        c = criteria[p.criterion_id]
        require(
            c["max_score"] == p.max_score and c["required_source_unit_ids"] == p.evidence_ids,
            "Structured score/evidence mismatch",
        )
    case.manifest["structured_definition_sha256"] = canonical_digest(exercise.model_dump())
    case.manifest["legacy_question_id"] = old
    return case, authored


def load_bundle(bundle, *, structured=False):
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    require(set(manifest["demo_ids"]) == DEMO_IDS, "Only the two reviewed demo IDs may import")
    cases = []
    for row in manifest["rows"]:
        if row["exercise_id"] not in DEMO_IDS:
            continue
        grading = json.loads(within(bundle, row["grading_path"]).read_text(encoding="utf-8"))
        learner = json.loads(within(bundle, row["learner_path"]).read_text(encoding="utf-8"))
        require(
            grading["expert_verified"] is False
            and grading["source_check_status"]
            == "checked_against_local_sources_not_expert_reviewed",
            "Source review missing",
        )
        require(
            grading["exercise_id"] == learner["exercise_id"] == row["exercise_id"],
            "Bundle identity mismatch",
        )
        require(
            all(
                key not in learner
                for key in ("criteria", "evidence", "source", "reference_answer", "annotations")
            ),
            "Grading data in learner payload",
        )
        require(len(grading["assets"]) == len(learner["images"]), "Asset mapping mismatch")
        for asset in grading["assets"]:
            path = within(bundle, asset["bundle_path"])
            require(digest(path) == asset["sha256"], "Asset SHA mismatch")
            require(asset["transformation"]["pixel_edits"] is False, "Unexpected image edit")
            magic = path.read_bytes()[:8]
            require(
                magic.startswith(b"\x89PNG\r\n\x1a\n") or magic.startswith(b"\xff\xd8"),
                "Not a supported image",
            )
        packet = grading["packet"]
        pdf = within(bundle, packet["path"])
        require(
            digest(pdf) == packet["sha256"] and pdf.read_bytes().startswith(b"%PDF-"),
            "Evidence packet changed",
        )
        qid = row["exercise_id"]
        source_id = "SRC_" + qid + "_PACKET"
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
            "expert_review_reason": (
                "Authored exercise; source checking is not clinical expert approval"
            ),
            "criteria": criteria,
        }
        units = [
            {
                "source_unit_id": e["source_unit_id"],
                "source_id": source_id,
                "title": "Evidence for " + e["source_unit_id"],
                "content": e["content_en"],
                "original_source_ref": e["source_ref"],
                "description_origin": e["description_origin"],
            }
            for e in grading["evidence"]
        ]
        payload = {
            "question": learner["presentation"] + "\n\n" + learner["question"],
            "student_answer": "Contract validation placeholder; no model call",
            "rubric": rubric,
            "evidence": [
                dict(
                    source_unit_id=u["source_unit_id"],
                    source_id=source_id,
                    title=u["title"],
                    page_start=1,
                    page_end=packet["pages"],
                    content=u["content"],
                )
                for u in units
            ],
        }
        EvaluationRequest.model_validate(payload)
        require(
            sum(c["max_score"] for c in criteria) == grading["max_score"], "Rubric total mismatch"
        )
        require(
            {sid for c in criteria for sid in c["required_source_unit_ids"]}
            == {u["source_unit_id"] for u in units},
            "Criterion evidence mismatch",
        )
        authored = {
            "learner": learner,
            "assets": grading["assets"],
            "criteria": grading["criteria"],
            "source": grading["source"],
            "answer_annotations": grading["answer_annotations"],
            "show_grid": row["kind"] == "authored_imaging",
            "packet_page_basis": packet["page_basis"],
            "expert_verified": False,
        }
        question = {
            "question_id": qid,
            "question": payload["question"],
            "reference_answer": "\n".join(c["reference_answer_vi"] for c in grading["criteria"]),
            "difficulty": "development_demo",
            "authored_exercise": True,
        }
        m = {
            "source_document": {"repo_relative_path": "clinical-cases/exercises/" + packet["path"]},
            "locator": {
                "chapter": "Compiled evidence packet",
                "section": qid,
                "pdf_pages": {"start": 1, "end": packet["pages"]},
                "printed_pages": None,
            },
            "evidence_verification": {
                "status": "checked_against_original_XML_or_annotations",
                "page_basis": packet["page_basis"],
                "source_refs": [e["source_ref"] for e in grading["evidence"]],
            },
            "expert_review": {"status": "unverified", "required": True},
            "clinical_exercise": authored,
            "compiled_packet_sha256": packet["sha256"],
            "bundle_definition_sha256": canonical_digest({"learner": learner, "grading": grading}),
        }
        catalog = {
            "source_id": source_id,
            "title": "Compiled evidence packet " + qid,
            "file_name": pdf.name,
            "original_sources": [grading["source"]],
            "page_basis": packet["page_basis"],
        }
        case = CaseInput(
            m,
            catalog,
            question,
            rubric,
            units,
            pdf,
            packet["sha256"],
            "clinical-cases/exercises/manifest.json",
        )
        cases.append(
            structured_revision(case, authored, bundle) if structured else (case, authored)
        )
    require(len(cases) == 2, "Both reviewed demos required")
    return cases


async def import_demos(bundle, *, apply=False, structured=False):
    cfg = get_settings()
    url = make_url(cfg.database_url)
    require(
        cfg.app_env == "development"
        and url.host in {"db", "localhost", "127.0.0.1"}
        and (
            url.database == "medical_learning"
            or (url.database or "").startswith("medresident_test_")
        ),
        "Refusing non-local/development database",
    )
    require(not cfg.model_calls_enabled, "This demo import requires model calls disabled")
    require(engine.dialect.name == "postgresql", "PostgreSQL required")
    rows = load_bundle(bundle.resolve(), structured=structured)
    storage = LocalFileStorage(cfg.file_storage_path)
    results = []
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
            connection = await session.connection()
            await connection.run_sync(lambda conn: assert_current_schema(conn, require_head=True))
            admin = await session.scalar(
                select(User)
                .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
                .order_by(User.id)
            )
            require(admin is not None, "An existing active administrator is required")
            for case, authored in rows:
                from app.modules.questions.models import Question

                existing = await session.scalar(
                    select(Question).where(Question.external_id == case.question["question_id"])
                )
                # Existing importer compares all metadata. Place clinical data in its existing
                # dataset_fields envelope so re-import remains an exact no-op.
                case.question["clinical_exercise"] = authored
                changed = await persist_case(session, case, admin.id)
                # This dedicated key is deliberately projected by the practice router.
                q = await session.scalar(
                    select(Question).where(Question.external_id == case.question["question_id"])
                )
                # Retain importer-owned metadata unmodified; access through dataset_fields below.
                if existing is None:
                    require(q is not None, "Question persistence failed")
                if apply:
                    publish_pdf(storage, case.storage_key, case.pdf, case.sha256)
                    for asset in authored["assets"]:
                        publish_pdf(
                            storage,
                            asset["storage_key"],
                            within(bundle, asset["bundle_path"]),
                            asset["sha256"],
                        )
                results.append(
                    {
                        "question_id": case.question["question_id"],
                        "action": "create" if changed else "unchanged",
                    }
                )
            if not apply:
                await session.rollback()
    return {
        "mode": "applied" if apply else "dry_run_rolled_back",
        "provider": cfg.practice_provider,
        "model_calls_enabled": False,
        "questions": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--structured", action="store_true", help="Import V2 structured revisions")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                asyncio.run(
                    import_demos(args.bundle, apply=args.apply, structured=args.structured)
                ),
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        # Avoid connection-string/secret or SQL-parameter logs.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
