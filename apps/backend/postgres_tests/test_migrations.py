import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

BACKEND = Path(__file__).resolve().parents[1]


async def alembic(engine, revision):
    env = {
        **os.environ,
        "DATABASE_URL": engine.url.render_as_string(hide_password=False),
        "DEBUG": "false",
    }

    def command():
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        # Only test DB data is involved, but don't include raw DB errors/URLs in failures.
        assert result.returncode == 0, "Alembic failed against disposable PostgreSQL"

    await asyncio.to_thread(command)
    # External DDL invalidates asyncpg prepared plans on existing connections.
    await engine.dispose()


async def require_vector(engine):
    async with engine.connect() as connection:
        available = await connection.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name='vector')")
        )
    if not available:
        pytest.skip("Full 0001 migration requires pgvector; PostgreSQL installation lacks vector")


async def test_new_database_baseline_then_head(pg_engine):
    await require_vector(pg_engine)
    await alembic(pg_engine, "20260714_0001")
    async with pg_engine.connect() as c:
        names = await c.run_sync(lambda conn: inspect(conn).get_table_names())
        columns = await c.run_sync(lambda conn: inspect(conn).get_columns("questions"))
        assert "source_units" not in names
        assert "external_id" not in {x["name"] for x in columns}
        assert not next(x for x in columns if x["name"] == "topic_id")["nullable"]
    await alembic(pg_engine, "head")
    async with pg_engine.connect() as c:
        from app.integration.schema import assert_current_schema

        await c.run_sync(lambda conn: assert_current_schema(conn, require_head=True))


async def test_upgrade_preserves_legacy_data(pg_engine):
    await require_vector(pg_engine)
    await alembic(pg_engine, "20260714_0001")
    user_id = uuid.uuid4()
    async with pg_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO users(id,email,hashed_password,full_name,role,is_active) "
                "VALUES(:id,'legacy@example.invalid','hash','Legacy','ADMIN',true)"
            ),
            {"id": user_id},
        )
    await alembic(pg_engine, "head")
    async with pg_engine.connect() as c:
        assert (
            await c.scalar(text("SELECT full_name FROM users WHERE id=:id"), {"id": user_id})
            == "Legacy"
        )


async def test_unversioned_nonempty_database_is_not_stamped(pg_engine):
    from app.integration.schema import assert_current_schema

    async with pg_engine.begin() as c:
        await c.execute(text("CREATE TABLE unexpected_table(id integer)"))
        with pytest.raises(RuntimeError, match="Schema drift"):
            await c.run_sync(assert_current_schema)
        assert await c.scalar(text("SELECT to_regclass('alembic_version')")) is None


async def test_0002_matches_orm_except_unavailable_vector_table(imported_schema):
    import sqlalchemy as sa

    from app.core.database import Base
    from app.integration.schema import assert_schema

    engine, _ = imported_schema
    expected = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name != "document_chunks":
            table.to_metadata(expected)
    async with engine.connect() as c:
        await c.run_sync(lambda conn: assert_schema(conn, expected))


async def test_0002_preserves_legacy_rows_without_vector_table(pg_engine):
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.integration.schema import frozen_baseline

    baseline = frozen_baseline()
    tables = [t for t in baseline.sorted_tables if t.name != "document_chunks"]
    user, specialty, topic, question, rubric, criterion = [uuid.uuid4() for _ in range(6)]
    async with pg_engine.begin() as c:
        await c.run_sync(lambda conn: baseline.create_all(conn, tables=tables))
        statements = [
            (
                "INSERT INTO users(id,email,hashed_password,full_name,role,is_active) "
                "VALUES(:id,'legacy@example.invalid','hash','Legacy','ADMIN',true)",
                {"id": user},
            ),
            (
                "INSERT INTO specialties(id,name) VALUES(:id,'Existing specialty')",
                {"id": specialty},
            ),
            (
                "INSERT INTO topics(id,specialty_id,name) VALUES(:id,:specialty,'Existing topic')",
                {"id": topic, "specialty": specialty},
            ),
            (
                "INSERT INTO questions(id,topic_id,question_type,content,created_by) "
                "VALUES(:id,:topic,'SHORT_ANSWER','Existing content',:user)",
                {"id": question, "topic": topic, "user": user},
            ),
            (
                "INSERT INTO rubrics(id,question_id,name,max_score) "
                "VALUES(:id,:q,'Existing rubric',3)",
                {"id": rubric, "q": question},
            ),
            (
                "INSERT INTO rubric_criteria(id,rubric_id,description,score,criterion_order) "
                "VALUES(:id,:r,'Existing criterion',3,1)",
                {"id": criterion, "r": rubric},
            ),
        ]
        for sql, params in statements:
            await c.execute(text(sql), params)
        names = ("users", "specialties", "topics", "questions", "rubrics", "rubric_criteria")
        snapshots = {}
        for name in names:
            snapshots[name] = dict((await c.execute(text(f"SELECT * FROM {name}"))).one()._mapping)

        def upgrade(conn):
            spec = importlib.util.spec_from_file_location(
                "_test_upgrade", BACKEND / "alembic/versions/20261020_0002_integration_evidence.py"
            )
            revision = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(revision)
            with Operations.context(MigrationContext.configure(conn)):
                revision.upgrade()

        await c.run_sync(upgrade)
        for name, before in snapshots.items():
            after = dict((await c.execute(text(f"SELECT * FROM {name}"))).one()._mapping)
            assert {key: after[key] for key in before} == before


async def test_0002_to_0003_preserves_imported_identity(pg_engine):
    await require_vector(pg_engine)
    await alembic(pg_engine, "20261020_0002")
    user, question = uuid.uuid4(), uuid.uuid4()
    async with pg_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO users(id,email,hashed_password,full_name,role,is_active) "
                "VALUES(:id,'preserve@example.invalid','not-login','Preserve','ADMIN',true)"
            ),
            {"id": user},
        )
        await c.execute(
            text(
                "INSERT INTO questions(id,question_type,content,created_by,"
                "external_id,import_metadata) "
                "VALUES(:id,'SHORT_ANSWER','Preserved question',:user,"
                "'preserved-external-id',CAST(:meta AS jsonb))"
            ),
            {"id": question, "user": user, "meta": '{"review":"unverified"}'},
        )
        before = dict(
            (await c.execute(text("SELECT * FROM questions WHERE id=:id"), {"id": question}))
            .one()
            ._mapping
        )
    await alembic(pg_engine, "20261022_0003")
    async with pg_engine.connect() as c:
        after = dict(
            (await c.execute(text("SELECT * FROM questions WHERE id=:id"), {"id": question}))
            .one()
            ._mapping
        )
        assert before == after
        assert await c.scalar(text("SELECT count(*) FROM practice_attempts")) == 0
        assert await c.scalar(text("SELECT version_num FROM alembic_version")) == "20261022_0003"
