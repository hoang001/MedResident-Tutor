import ast
import json
import uuid

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integration import importer
from app.integration.inputs import CaseConflict, CaseError, digest, load_case
from app.integration.reader import medical_payload
from app.integration.schema import assert_current_schema, frozen_baseline
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit
from app.modules.questions.models import (
    Question,
    Rubric,
    RubricCriterion,
    RubricCriterionSourceUnit,
)
from postgres_tests.conftest import MANIFEST, REPO

QID = "ORTHO_B21CN1_Q_0001"
TABLES = (Document, SourceUnit, Question, Rubric, RubricCriterion, RubricCriterionSourceUnit)


async def counts(engine):
    async with AsyncSession(engine) as s:
        return [await s.scalar(select(func.count()).select_from(model)) for model in TABLES]


def update_manifest(root, change):
    path = root / MANIFEST
    m = json.loads(path.read_text(encoding="utf-8"))
    change(m)
    path.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


def test_input_and_baseline(case_repo):
    case = load_case(case_repo, MANIFEST)
    assert len(case.rubric["criteria"]) == 2
    assert case.rubric["max_score"] == 2
    assert len(case.units) == 1
    baseline = frozen_baseline()
    assert len(baseline.tables) == 19
    assert "source_units" not in baseline.tables
    assert "external_id" not in baseline.tables["documents"].c
    assert not baseline.tables["questions"].c.topic_id.nullable


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m["source_document"].update(sha256="0" * 64),
        lambda m: m.update(source_unit_ids=["MISSING_UNIT"]),
        lambda m: m["locator"]["pdf_pages"].update(start=0),
        lambda m: m["existing_dataset_flags"]["question"].update(expert_review_required=True),
    ],
)
def test_prevalidation_rejects(case_repo, mutation):
    update_manifest(case_repo, mutation)
    with pytest.raises(CaseError):
        load_case(case_repo, MANIFEST)


async def test_import_noop_and_payload(imported_schema, case_repo, tmp_path):
    engine, admin = imported_schema
    storage = tmp_path / "storage"
    before = digest(load_case(case_repo, MANIFEST).pdf)
    result = await importer.import_case(engine, case_repo, MANIFEST, admin, storage)
    assert result["status"] == "imported"
    assert await counts(engine) == [1, 1, 1, 1, 2, 2]
    copied = storage / result["storage_key"]
    stamp = copied.stat().st_mtime_ns
    assert digest(copied) == before
    assert (await importer.import_case(engine, case_repo, MANIFEST, admin, storage))[
        "status"
    ] == "already_imported"
    assert await counts(engine) == [1, 1, 1, 1, 2, 2]
    assert copied.stat().st_mtime_ns == stamp
    async with AsyncSession(engine) as s:
        q = await s.scalar(select(Question))
        su = await s.scalar(select(SourceUnit))
        assert q.topic_id is None
        assert (su.pdf_page_start, su.pdf_page_end, su.printed_page_start) == (16, 16, 15)
        assert su.import_metadata["dataset_fields"]["page_end"] == 17
        assert su.import_metadata["dataset_fields"]["scope_status"] == "provisional"
        payload = await medical_payload(s, QID, "Runtime answer only")
        assert len(payload["rubric"]["criteria"]) == 2
        assert payload["rubric"]["max_score"] == 2
        assert len(payload["evidence"]) == 1
        assert payload["evidence"][0]["source_unit_id"] == "ORTHO_B21CN1_KU_0001"
        assert payload["evidence"][0]["page_end"] == 16
        assert payload["student_answer"] == "Runtime answer only"
        assert "reference_answer" not in json.dumps(payload)
        assert "import_metadata" not in json.dumps(payload)
        raw = load_case(case_repo, MANIFEST)
        assert payload["rubric"] == raw.rubric
        assert payload["evidence"][0]["content"] == raw.units[0]["content"]
        # Execute only the pure builder AST: importing the pilot module makes directories.
        tree = ast.parse(
            (REPO / "model-training/src/medical/inference.py").read_text(encoding="utf-8")
        )
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "build_user_content"
        )
        namespace = {"json": json}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "pilot_builder", "exec"), namespace)
        assert json.loads(namespace["build_user_content"](payload)) == payload


@pytest.mark.parametrize("change", ["content", "links", "extra_criterion"])
async def test_db_conflicts_rollback(imported_schema, case_repo, tmp_path, change):
    engine, admin = imported_schema
    storage = tmp_path / "storage"
    await importer.import_case(engine, case_repo, MANIFEST, admin, storage)
    async with AsyncSession(engine) as s, s.begin():
        c = await s.scalar(select(RubricCriterion))
        if change == "content":
            c.description = "Changed externally"
        elif change == "links":
            link = await s.get(
                RubricCriterionSourceUnit, (c.id, await s.scalar(select(SourceUnit.id)))
            )
            await s.delete(link)
        else:
            s.add(
                RubricCriterion(
                    rubric_id=c.rubric_id, description="Extra", score=1, criterion_order=10
                )
            )
    before = await counts(engine)
    stored = next(storage.rglob("*.pdf"))
    with pytest.raises(CaseConflict):
        await importer.import_case(engine, case_repo, MANIFEST, admin, storage)
    assert await counts(engine) == before
    assert stored.is_file()  # A pre-existing file is never cleaned up.


@pytest.mark.parametrize("failure", ["hash", "reference", "admin"])
async def test_prevalidation_does_not_write(imported_schema, case_repo, tmp_path, failure):
    engine, admin = imported_schema
    storage = tmp_path / "storage"
    if failure == "hash":
        update_manifest(case_repo, lambda m: m["source_document"].update(sha256="0" * 64))
    elif failure == "reference":
        update_manifest(case_repo, lambda m: m.update(source_unit_ids=["MISSING_UNIT"]))
    else:
        admin = uuid.uuid4()
    with pytest.raises(CaseError):
        await importer.import_case(engine, case_repo, MANIFEST, admin, storage)
    assert await counts(engine) == [0] * 6
    assert not storage.exists()


async def test_mid_transaction_failure(imported_schema, case_repo, tmp_path, monkeypatch):
    engine, admin = imported_schema
    original = importer.ensure_row

    async def fail_after_question(session, model, external_id, values):
        result = await original(session, model, external_id, values)
        if model is Question:
            raise RuntimeError("Injected mid-transaction failure")
        return result

    monkeypatch.setattr(importer, "ensure_row", fail_after_question)
    with pytest.raises(RuntimeError, match="Injected"):
        await importer.import_case(engine, case_repo, MANIFEST, admin, tmp_path / "storage")
    assert await counts(engine) == [0] * 6
    assert not list((tmp_path / "storage").rglob("*.pdf"))


@pytest.mark.parametrize("preexisting_file", [False, True])
async def test_commit_failure_cleans_only_new_file(
    imported_schema, case_repo, tmp_path, preexisting_file
):
    engine, admin = imported_schema
    storage = tmp_path / "storage"
    if preexisting_file:
        from app.storage.local import LocalFileStorage

        case = load_case(case_repo, MANIFEST)
        importer.publish_pdf(LocalFileStorage(storage), case.storage_key, case.pdf, case.sha256)

    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "commit", once=True)
    def fail_commit(connection):
        raise RuntimeError("Injected commit failure")

    with pytest.raises(RuntimeError, match="Injected commit"):
        await importer.import_case(engine, case_repo, MANIFEST, admin, storage)
    assert await counts(engine) == [0] * 6
    assert bool(list(storage.rglob("*.pdf"))) == preexisting_file


async def test_uncertain_commit_preserves_referenced_file(imported_schema, case_repo, tmp_path):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    engine, admin = imported_schema

    def fail_after_commit(session):
        raise RuntimeError("Injected lost acknowledgement after commit")

    event.listen(Session, "after_commit", fail_after_commit, once=True)
    try:
        with pytest.raises(RuntimeError, match="lost acknowledgement"):
            await importer.import_case(engine, case_repo, MANIFEST, admin, tmp_path / "storage")
        assert await counts(engine) == [1, 1, 1, 1, 2, 2]
        assert len(list((tmp_path / "storage").rglob("*.pdf"))) == 1
    finally:
        event.remove(Session, "after_commit", fail_after_commit)


async def test_postgres_constraints(imported_schema, case_repo, tmp_path):
    engine, admin = imported_schema
    await importer.import_case(engine, case_repo, MANIFEST, admin, tmp_path / "storage")
    async with engine.connect() as c:
        columns = await c.run_sync(lambda conn: inspect(conn).get_columns("source_units"))
        assert str(next(x["type"] for x in columns if x["name"] == "import_metadata")) == "JSONB"
    async with AsyncSession(engine) as s:
        unit = await s.scalar(select(SourceUnit))
        await s.rollback()
        with pytest.raises(IntegrityError):
            await s.execute(text("UPDATE source_units SET pdf_page_start = 0"))
            await s.commit()
        await s.rollback()
        with pytest.raises(IntegrityError):
            await s.execute(text("UPDATE source_units SET document_id = :id"), {"id": uuid.uuid4()})
            await s.commit()
        await s.rollback()
        assert unit is not None


async def test_unversioned_schema_refused(imported_schema):
    engine, _ = imported_schema
    async with engine.connect() as c:
        with pytest.raises(RuntimeError, match="requires Alembic head"):
            await c.run_sync(lambda conn: assert_current_schema(conn, require_head=True))
