"""Read-only verification that UI work did not alter real learning/bank data."""
import asyncio
import json
import sys

from .common import ROOT, digest, inside, read, sha, write


async def verify():
    from sqlalchemy import text
    import app.models  # noqa: F401
    from app.core.config import get_settings
    from app.core.database import engine

    before = read('database-before.json')
    after = {}
    async with engine.connect() as connection:
        await connection.execute(text('SET TRANSACTION READ ONLY'))
        for table in before:
            assert table.replace('_', '').isalnum()
            rows = (await connection.execute(text('SELECT row_to_json(t)::text FROM ' + table + ' t'))).scalars().all()
            after[table] = dict(count=len(rows), row_hashes=sorted(digest(json.loads(row)) for row in rows))
        available = await connection.scalar(text('SELECT count(*) FROM questions WHERE is_available'))
    write('database-after.json', after)
    changed_tables = [table for table in before if before[table] != after[table]]
    protected = read('bank-and-locked-data-hashes.json')
    changed_files = [path for path, expected in protected.items() if not (ROOT / path).is_file() or sha(ROOT / path) != expected]
    settings = get_settings()
    report = dict(main_database_unchanged=not changed_tables, changed_tables=changed_tables,
                  bank_and_locked_files_unchanged=not changed_files, changed_files=changed_files,
                  counts={key: value['count'] for key, value in after.items()}, available_questions=available,
                  practice_provider=settings.practice_provider, model_calls_enabled=settings.model_calls_enabled,
                  authoring_provider=settings.authoring_provider, executed_model_calls=0,
                  notes='No OCR, extraction, training, model loading, KG writes or main-DB writes in this UI task.')
    write('data-preservation.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'counts'}))
    assert not changed_tables and not changed_files


if __name__ == '__main__':
    asyncio.run(verify()) if '--inside' in sys.argv else inside('verify')
