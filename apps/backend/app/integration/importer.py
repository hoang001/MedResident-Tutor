import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.common.enums import DocumentProcessingStatus, QuestionType, UserRole
from app.integration.inputs import CaseConflict, CaseInput, canonical_digest, load_case, require
from app.integration.schema import assert_current_schema
from app.integration.storage import publish_pdf
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.questions.models import (
    Question,
    Rubric,
    RubricCriterion,
    RubricCriterionSourceUnit,
)
from app.modules.users.models import User
from app.storage.local import LocalFileStorage

# Serialize the small explicit importer, including cleanup after uncertain commit outcomes.
# This is a PostgreSQL transaction lock, not a new infrastructure service.
IMPORT_LOCK = 64912357012026


def remainder(row: dict, mapped: set[str]) -> dict:
    return {k: v for k, v in row.items() if k not in mapped}


def metadata(row: dict, mapped: set[str]) -> dict:
    return {"dataset_fields": remainder(row, mapped), "input_record_sha256": canonical_digest(row)}


async def ensure_row(session, model, external_id: str, values: dict):
    existing = await session.scalar(select(model).where(model.external_id == external_id))
    if existing:
        changed = [key for key, value in values.items() if getattr(existing, key) != value]
        if changed:
            raise CaseConflict(f"{model.__tablename__}:{external_id} conflict: {','.join(changed)}")
        return existing, False
    row = model(external_id=external_id, **values)
    session.add(row)
    await session.flush()
    return row, True


async def persist_case(session: AsyncSession, case: CaseInput, admin_id: uuid.UUID) -> bool:
    """No commit here. The caller owns the entire transaction."""
    admin = await session.get(User, admin_id)
    require(
        admin is not None and admin.is_active and admin.role == UserRole.ADMIN,
        "created-by must reference an existing active admin",
    )
    m, q, r = case.manifest, case.question, case.rubric
    doc_metadata = {
        "catalog": case.catalog,
        "manifest": m,
        "manifest_path": case.manifest_path,
        "manifest_sha256": canonical_digest(m),
        "importer_version": "1.0.0",
        "source_repo_relative_path": m["source_document"]["repo_relative_path"],
        "storage_kind": "upload_root_relative",
    }
    document, document_new = await ensure_row(
        session,
        Document,
        case.catalog["source_id"],
        {
            "name": case.catalog["title"],
            "original_filename": case.pdf.name,
            "storage_path": case.storage_key,
            "mime_type": "application/pdf",
            "file_size": case.pdf.stat().st_size,
            "source_name": case.catalog["title"],
            "source_url": None,
            "version": "1",
            "processing_status": DocumentProcessingStatus.UPLOADED,
            "processing_error": None,
            "created_by": admin_id,
            "topic_id": None,
            "specialty_id": None,
            "source_sha256": case.sha256,
            "import_metadata": doc_metadata,
        },
    )
    units = {}
    new_flags = [document_new]
    loc = m["locator"]
    for u in case.units:
        unit_metadata = metadata(u, {"source_unit_id", "source_id", "title", "content"})
        unit_metadata.update(
            {
                "locator_basis": "integration_manifest_original_pdf_comparison",
                "evidence_verification": m["evidence_verification"],
                "expert_review": m["expert_review"],
            }
        )
        printed = loc.get("printed_pages") or {}
        su, is_new = await ensure_row(
            session,
            SourceUnit,
            u["source_unit_id"],
            {
                "document_id": document.id,
                "title": u["title"],
                "content": u["content"],
                "chapter": loc["chapter"],
                "section": loc["section"],
                "subsection": loc.get("subsection"),
                "pdf_page_start": loc["pdf_pages"]["start"],
                "pdf_page_end": loc["pdf_pages"]["end"],
                "printed_page_start": printed.get("start"),
                "printed_page_end": printed.get("end"),
                "import_metadata": unit_metadata,
            },
        )
        units[u["source_unit_id"]] = su
        new_flags.append(is_new)
    question, question_new = await ensure_row(
        session,
        Question,
        q["question_id"],
        {
            "topic_id": None,
            "created_by": admin_id,
            "question_type": QuestionType.SHORT_ANSWER,
            "content": q["question"],
            "reference_answer": q.get("reference_answer"),
            "explanation": None,
            "difficulty": q.get("difficulty"),
            "import_metadata": metadata(
                q, {"question_id", "question", "reference_answer", "difficulty"}
            ),
        },
    )
    if question_new:
        # A validated integration import retains its prior immediate-practice behavior.
        # Re-import never changes an existing administrator availability decision.
        question.is_available = True
    new_flags.append(question_new)
    # Do not attach a new external ID to another rubric already owned by this question.
    owned = await session.scalar(select(Rubric).where(Rubric.question_id == question.id))
    if owned and owned.external_id != r["rubric_id"]:
        raise CaseConflict("Question already owns a different rubric")
    rubric, rubric_new = await ensure_row(
        session,
        Rubric,
        r["rubric_id"],
        {
            "question_id": question.id,
            "name": r["rubric_id"],
            "max_score": r["max_score"],
            "import_metadata": metadata(r, {"rubric_id", "question_id", "max_score", "criteria"}),
        },
    )
    new_flags.append(rubric_new)
    old_criteria = list(
        await session.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id))
    )
    expected_ids = {c["criterion_id"] for c in r["criteria"]}
    if not rubric_new and {c.external_id for c in old_criteria} != expected_ids:
        raise CaseConflict("Existing rubric criterion membership differs")
    for order, c in enumerate(r["criteria"], 1):
        criterion, criterion_new = await ensure_row(
            session,
            RubricCriterion,
            c["criterion_id"],
            {
                "rubric_id": rubric.id,
                "description": c["description"],
                "score": c["max_score"],
                "criterion_order": order,
                "required_concepts": None,
                "import_metadata": metadata(
                    c, {"criterion_id", "description", "max_score", "required_source_unit_ids"}
                ),
            },
        )
        new_flags.append(criterion_new)
        links = list(
            await session.scalars(
                select(RubricCriterionSourceUnit)
                .where(RubricCriterionSourceUnit.criterion_id == criterion.id)
                .order_by(RubricCriterionSourceUnit.evidence_order)
            )
        )
        expected = [(units[key].id, i) for i, key in enumerate(c["required_source_unit_ids"], 1)]
        if not criterion_new:
            if [(link.source_unit_id, link.evidence_order) for link in links] != expected:
                raise CaseConflict("Existing criterion evidence membership/order differs")
        else:
            session.add_all(
                [
                    RubricCriterionSourceUnit(
                        criterion_id=criterion.id, source_unit_id=unit_id, evidence_order=i
                    )
                    for unit_id, i in expected
                ]
            )
    # Existing fragments are not repaired implicitly. An import is all-new or a no-op.
    if any(new_flags) and not all(new_flags):
        raise CaseConflict("Partial existing case: explicit reconciliation required")
    await session.flush()
    return all(new_flags)


async def cleanup_if_unreferenced(
    engine: AsyncEngine, storage: LocalFileStorage, case: CaseInput
) -> None:
    # A fresh transaction can see whether a commit actually reached PostgreSQL.
    # If this check cannot be completed, preserve the file (safe orphan).
    async with engine.begin() as connection:
        await connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
        referenced = await connection.scalar(
            select(Document.id).where(Document.storage_path == case.storage_key).limit(1)
        )
        if referenced is None:
            from app.integration.inputs import digest

            target = storage._resolve(case.storage_key)
            if target.is_file() and await asyncio.to_thread(digest, target) == case.sha256:
                await asyncio.to_thread(target.unlink)


async def import_case(
    engine: AsyncEngine,
    repo_root: Path,
    manifest_path: Path,
    admin_id: uuid.UUID,
    storage_root: Path,
) -> dict:
    require(engine.dialect.name == "postgresql", "Integration import requires PostgreSQL")
    case = await asyncio.to_thread(load_case, repo_root, manifest_path)
    storage = LocalFileStorage(storage_root)
    created_file = False
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
            connection = await session.connection()
            await connection.run_sync(lambda conn: assert_current_schema(conn, require_head=True))
            changed = await persist_case(session, case, admin_id)
            # No source copying before all DB conflict checks have succeeded.
            created_file = await asyncio.to_thread(
                publish_pdf, storage, case.storage_key, case.pdf, case.sha256
            )
        return {
            "status": "imported" if changed else "already_imported",
            "question_id": case.question["question_id"],
            "storage_key": case.storage_key,
        }
    except BaseException:
        if created_file:
            try:
                await asyncio.shield(cleanup_if_unreferenced(engine, storage, case))
            except Exception:
                # No deletion on an unknown DB outcome. A later no-op import reuses the file.
                pass
        raise
