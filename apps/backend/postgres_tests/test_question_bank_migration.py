import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.source_units import SourceUnit
from app.modules.questions.models import Rubric, RubricCriterion, RubricCriterionSourceUnit
from postgres_tests.test_migrations import alembic, require_vector
from tests.e2e.bank_fixtures import seed_sources


async def test_upgrade_bank_preserves_legacy_question_snapshot_and_availability(
    pg_engine, tmp_path
):
    await require_vector(pg_engine)
    await alembic(pg_engine, "20261022_0003")
    admin, qid, rid, cid, aid = [uuid.uuid4() for _ in range(5)]
    async with AsyncSession(pg_engine) as s, s.begin():
        # This database is deliberately at 0003: newer ORM columns do not exist yet.
        await s.execute(
            text(
                "INSERT INTO users(id,email,full_name,hashed_password,role,is_active) "
                "VALUES(:id,'migration-bank@example.com','Fixture','not-login','ADMIN',true)"
            ),
            {"id": admin},
        )
        await s.flush()
        await seed_sources(s, admin, tmp_path / "sources")
        await s.execute(
            text(
                "INSERT INTO questions(id,question_type,content,created_by,"
                "external_id,import_metadata) "
                "VALUES(:q,'SHORT_ANSWER','Keep original',:u,'LEGACY_Q',CAST(:meta AS jsonb))"
            ),
            {"q": qid, "u": admin, "meta": '{"review":"unverified","original":true}'},
        )
        s.add(Rubric(id=rid, question_id=qid, external_id="LEGACY_R", name="Legacy", max_score=1))
        await s.flush()
        s.add(
            RubricCriterion(
                id=cid,
                rubric_id=rid,
                external_id="LEGACY_C",
                description="Preserve",
                score=1,
                criterion_order=1,
            )
        )
        await s.flush()
        source = await s.scalar(
            select(SourceUnit)
            .where(SourceUnit.external_id == "FIXTURE_SU_A")
        )
        s.add(
            RubricCriterionSourceUnit(criterion_id=cid, source_unit_id=source.id, evidence_order=1)
        )
        await s.execute(
            text(
                "INSERT INTO practice_attempts(id,user_id,question_id,idempotency_key,input_hash,"
                "student_answer,status,execution_mode,snapshot,provider_metadata) "
                "VALUES(:id,:u,:q,'legacy',:hash,'Keep answer','completed','mock',"
                "CAST(:snap AS jsonb),'{}')"
            ),
            {
                "id": aid,
                "u": admin,
                "q": qid,
                "hash": "a" * 64,
                "snap": '{"old_snapshot":"retain exactly"}',
            },
        )
    async with pg_engine.connect() as c:
        before = dict(
            (await c.execute(text("SELECT * FROM questions WHERE id=:q"), {"q": qid}))
            .one()
            ._mapping
        )
        snapshot = await c.scalar(
            text("SELECT to_jsonb(t)::text FROM practice_attempts t WHERE id=:id"), {"id": aid}
        )
    await alembic(pg_engine, "head")
    # DDL ran in another process: discard asyncpg prepared plans from before ALTER.
    await pg_engine.dispose()
    async with pg_engine.connect() as c:
        after = dict(
            (await c.execute(text("SELECT * FROM questions WHERE id=:q"), {"q": qid}))
            .one()
            ._mapping
        )
        assert {k: after[k] for k in before} == before
        assert after["is_available"] is True and after["bank_version"] == 1
        assert (
            await c.scalar(
                text("SELECT to_jsonb(t)::text FROM practice_attempts t WHERE id=:id"), {"id": aid}
            )
            == snapshot
        )
        from app.integration.schema import assert_current_schema

        await c.run_sync(lambda conn: assert_current_schema(conn, require_head=True))
