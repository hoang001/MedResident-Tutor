"""Read-only drift checks; never stamp or repair an existing database."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

BASELINE = "20260714_0001"
INTEGRATION = "20261020_0002"
PRACTICE = "20261022_0003"
QUESTION_BANK = "20261022_0004"
HEAD = "20261027_0005"


def frozen_baseline() -> sa.MetaData:
    path = Path(__file__).resolve().parents[2] / "alembic/versions/20260714_0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("_frozen_foundation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = sa.MetaData()

    class Recorder:
        @staticmethod
        def execute(_sql):
            pass  # Extension DDL has no table metadata.

        @staticmethod
        def f(name):
            return name

        @staticmethod
        def create_table(name, *items, **kwargs):
            return sa.Table(name, metadata, *items, **kwargs)

        @staticmethod
        def create_index(name, table, columns, unique=False):
            sa.Index(name, *(metadata.tables[table].c[c] for c in columns), unique=unique)

    module.op = Recorder()
    module.upgrade()
    return metadata


def assert_schema(connection, expected: sa.MetaData) -> None:
    context = MigrationContext.configure(
        connection, opts={"compare_type": True, "compare_server_default": True}
    )
    changes = compare_metadata(context, expected)
    if changes:
        # Do not print SQL reprs or connection information.
        raise RuntimeError(f"Schema drift detected ({len(changes)} differences); no repair applied")
    inspector = sa.inspect(connection)
    # Alembic comparison does not cover CHECK constraints.
    for table in expected.tables.values():
        actual_checks = {c["name"] for c in inspector.get_check_constraints(table.name)}
        required_checks = {
            c.name for c in table.constraints if isinstance(c, sa.CheckConstraint) and c.name
        }
        if not required_checks <= actual_checks:
            raise RuntimeError(f"Missing CHECK constraint in {table.name}")


def assert_current_schema(connection, *, require_head: bool = False) -> None:
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Migration/integration schema checks require PostgreSQL")
    revision = MigrationContext.configure(connection).get_current_revision()
    if require_head and revision != HEAD:
        raise RuntimeError("Integration requires Alembic head; run reviewed migrations explicitly")
    if revision is None:
        expected = sa.MetaData()
    elif revision == BASELINE:
        expected = frozen_baseline()
    elif revision in (INTEGRATION, PRACTICE, QUESTION_BANK, HEAD):
        import app.models  # noqa: F401
        from app.core.database import Base

        if revision == HEAD:
            expected = Base.metadata
        else:
            expected = sa.MetaData()
            for table in Base.metadata.sorted_tables:
                if revision != INTEGRATION or table.name != "practice_attempts":
                    table.to_metadata(expected)
            users = expected.tables["users"]
            for constraint in list(users.constraints):
                if (
                    isinstance(constraint, sa.UniqueConstraint)
                    and "google_subject" in constraint.columns
                ):
                    users.constraints.remove(constraint)
            users._columns.remove(users.c.google_subject)
            if revision == QUESTION_BANK:
                assert_schema(connection, expected)
                return
            question = expected.tables["questions"]
            for constraint in list(question.constraints):
                if constraint.name == "ck_question_bank_version":
                    question.constraints.remove(constraint)
            question._columns.remove(question.c.is_available)
            question._columns.remove(question.c.bank_version)
    else:
        raise RuntimeError("Unknown Alembic revision; explicit schema reconciliation required")
    assert_schema(connection, expected)
