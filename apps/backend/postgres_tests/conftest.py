"""Tests require an explicitly named disposable PostgreSQL database.

When pgvector is unavailable, importer tests use the actual PostgreSQL ORM tables
except document_chunks (which needs vector). This does NOT validate migrations;
the migration tests skip explicitly. There is no production bypass flag.
"""

import errno
import importlib.util
import json
import os
import shutil
import uuid
from pathlib import Path

os.environ["DEBUG"] = "false"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

import app.models  # noqa: E402, F401
from app.common.enums import UserRole  # noqa: E402
from app.integration import importer  # noqa: E402
from app.integration.schema import frozen_baseline  # noqa: E402
from app.modules.users.models import User  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
MANIFEST = Path("data/integration/ORTHO_B21CN1_Q_0001.manifest.json")


@pytest.fixture
def case_repo(tmp_path):
    root = tmp_path / "repo"
    for name in (
        "processed/qa_items.jsonl",
        "processed/rubrics.jsonl",
        "processed/source_units.jsonl",
        "sources/source_catalog.jsonl",
        str(MANIFEST)[5:],
    ):
        source = REPO / "data" / name
        target = root / "data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    relative = manifest["source_document"]["repo_relative_path"]
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    # Test fixtures must never mutate this linked source PDF.
    try:
        os.link(REPO / relative, target)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        # Docker bind mounts and pytest temporary files can be on different devices.
        shutil.copyfile(REPO / relative, target)
    return root


@pytest.fixture
async def pg_engine():
    url = os.environ.get("INTEGRATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set INTEGRATION_TEST_DATABASE_URL to an isolated PostgreSQL database")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or not (parsed.database or "").startswith(
        "medresident_test_"
    ):
        pytest.fail("Refusing destructive tests: use postgresql+asyncpg / medresident_test_* DB")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def imported_schema(pg_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    # Actual JSONB/FK/check constraints on PostgreSQL. No SQLite substitution.
    baseline = frozen_baseline()
    tables = [t for t in baseline.sorted_tables if t.name != "document_chunks"]
    async with pg_engine.begin() as connection:
        await connection.run_sync(lambda conn: baseline.create_all(conn, tables=tables))

        # Exercise the actual 0002 DDL, not create_all of the new ORM.
        def upgrade_0002(conn):
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            path = REPO / "apps/backend/alembic/versions/20261020_0002_integration_evidence.py"
            spec = importlib.util.spec_from_file_location("_integration_revision", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
            path = REPO / "apps/backend/alembic/versions/20261022_0003_practice.py"
            spec = importlib.util.spec_from_file_location("_practice_revision", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()

        await connection.run_sync(upgrade_0002)

        def upgrade_0004(conn):
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            path = REPO / "apps/backend/alembic/versions/20261022_0004_question_bank.py"
            spec = importlib.util.spec_from_file_location("_bank_revision", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()

        await connection.run_sync(upgrade_0004)

        def upgrade_0005(conn):
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            path = REPO / "apps/backend/alembic/versions/20261027_0005_google_identity.py"
            spec = importlib.util.spec_from_file_location("_google_revision", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()

        await connection.run_sync(upgrade_0005)

    def partial_schema_check(connection, *, require_head=False):
        assert connection.dialect.name == "postgresql"
        # Full drift/revision checks are tested with migrations when vector is available.

    monkeypatch.setattr(importer, "assert_current_schema", partial_schema_check)
    admin_id = uuid.uuid4()
    async with AsyncSession(pg_engine) as session, session.begin():
        session.add(
            User(
                id=admin_id,
                email="integration@example.invalid",
                full_name="Test admin",
                hashed_password="not-a-login-hash",
                role=UserRole.ADMIN,
                is_active=True,
            )
        )
    return pg_engine, admin_id
