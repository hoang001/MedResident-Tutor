"""Run inside the existing backend, read-only. Never emits configuration secrets."""

import asyncio
import json

from neo4j import AsyncGraphDatabase, READ_ACCESS
from sqlalchemy import select, func

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.modules.practice.models import PracticeAttempt
from app.modules.questions.models import Question


async def main():
    settings = get_settings()
    out = {
        "provider": settings.practice_provider,
        "model_calls_enabled": settings.model_calls_enabled,
        "neo4j_configured": bool(settings.neo4j_uri and settings.neo4j_password),
    }
    async with SessionFactory() as session:
        out["practice_attempts"] = await session.scalar(
            select(func.count()).select_from(PracticeAttempt)
        )
        result = await session.scalars(
            select(Question).where(Question.is_available.is_(True))
        )
        out["questions"] = [
            {
                "id": q.external_id,
                "question": q.content,
                "metadata_keys": sorted(
                    (q.import_metadata or {}).get("dataset_fields", {})
                ),
                "authored_case": bool(
                    (q.import_metadata or {})
                    .get("dataset_fields", {})
                    .get("clinical_exercise")
                ),
            }
            for q in result
        ]
    driver = None
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            connection_timeout=4,
            connection_acquisition_timeout=4,
            max_transaction_retry_time=0,
        )
        async with driver.session(
            database=settings.neo4j_database, default_access_mode=READ_ACCESS
        ) as session:
            async with await session.begin_transaction(timeout=8) as tx:
                result = await tx.run(
                    "MATCH (n:MedicalConcept) RETURN count(n) AS count"
                )
                out["live_medical_node_count"] = (await result.single())["count"]
                result = await tx.run(
                    "MATCH (n:MedicalConcept) WHERE n.name CONTAINS 'Vết thương' "
                    "RETURN n.id AS id,n.name AS name,n.content AS content LIMIT 3"
                )
                out["live_bounded_sample"] = await result.data()
                out["neo4j_read_queries"] = 2
    except Exception as exc:
        out["neo4j_error_type"] = type(exc).__name__
        out["neo4j_error_message"] = (
            "Read-only Neo4j probe unavailable; connection details suppressed"
        )
    finally:
        if driver:
            await driver.close()
        await engine.dispose()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
