"""Explicit import/read commands. No migrations, seeds or model calls on startup."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # noqa: F401
from app.core.config import Settings
from app.integration.importer import import_case
from app.integration.inputs import CaseError
from app.integration.reader import medical_payload
from app.integration.schema import assert_current_schema


async def run(args) -> dict:
    # Explicit repo .env selection; environment variables still take precedence.
    # Never display the URL or a raw DB exception (it may include credentials).
    settings = Settings(_env_file=args.repo_root / ".env")
    engine = create_async_engine(settings.database_url)
    try:
        if args.command == "import":
            root = settings.file_storage_path
            if not root.is_absolute():
                root = args.repo_root / root
            return await import_case(engine, args.repo_root, args.manifest, args.created_by, root)
        if engine.dialect.name != "postgresql":
            raise CaseError("Integration reader requires PostgreSQL")
        async with AsyncSession(engine) as session, session.begin():
            # A consistent snapshot across all reader queries, without modifying records.
            from sqlalchemy import text

            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            connection = await session.connection()
            await connection.run_sync(lambda conn: assert_current_schema(conn, require_head=True))
            return await medical_payload(session, args.question_id, args.student_answer)
    finally:
        await engine.dispose()


def main() -> None:
    # Windows pipes may default to a legacy code page that cannot encode Vietnamese.
    # JSON CLI output is always UTF-8, including when stdout is redirected.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--manifest", type=Path, required=True)
    imp.add_argument("--created-by", type=uuid.UUID, required=True)
    read = sub.add_parser("payload")
    read.add_argument("--question-id", required=True)
    read.add_argument("--student-answer", required=True)
    args = parser.parse_args()
    args.repo_root = args.repo_root.resolve()
    try:
        result = asyncio.run(run(args))
    except CaseError as exc:
        print(f"Integration case rejected: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        print(
            f"Integration case failed ({type(exc).__name__}); no automatic retry or migration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
