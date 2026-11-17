"""Append <=12 supplement attempts to the SAME authorized benchmark ledger."""

import json
import sqlite3
from datetime import UTC, datetime

from .common import PARENT, RUN, read


def connection():
    db = sqlite3.connect(PARENT / "execution-ledger.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    return db


def reserve(config, sample_id, fingerprint):
    authorization = read(RUN / "authorization.json")
    if config not in {"retrieval_medical_vector_v1", "retrieval_medical_hybrid_v1"}:
        raise ValueError("Unknown supplemental config")
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        total = db.execute("SELECT count(*) FROM attempts").fetchone()[0]
        count = db.execute(
            "SELECT count(*) FROM attempts WHERE category='medical_retrieval_supplement'"
        ).fetchone()[0]
        if (
            total >= authorization["shared_total_ceiling"]
            or count >= authorization["supplement_max_attempts"]
        ):
            raise RuntimeError("SHARED_INFERENCE_BUDGET_EXHAUSTED")
        if db.execute(
            "SELECT id FROM attempts WHERE config=? AND sample_id=?",
            (config, sample_id),
        ).fetchone():
            raise RuntimeError("PREVIOUS_SUPPLEMENT_ATTEMPT_EXISTS_NO_RETRY")
        cursor = db.execute(
            "INSERT INTO attempts(config,sample_id,category,fingerprint,started,status) "
            "VALUES(?,?,'medical_retrieval_supplement',?,?,'started')",
            (config, sample_id, fingerprint, datetime.now(UTC).isoformat()),
        )
        return cursor.lastrowid


def started(identifier):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM attempts WHERE id=?", (identifier,)).fetchone()
        if (
            not row
            or row["category"] != "medical_retrieval_supplement"
            or row["generation_started"]
            or row["status"] != "started"
        ):
            raise RuntimeError("DUPLICATE_OR_UNAUTHORIZED_GENERATION")
        db.execute("UPDATE attempts SET generation_started=1 WHERE id=?", (identifier,))


def finish(identifier, status, reason=None):
    with connection() as db:
        db.execute(
            "UPDATE attempts SET status=?,finished=?,reason=? WHERE id=? AND category='medical_retrieval_supplement'",
            (
                status,
                datetime.now(UTC).isoformat(),
                json.dumps(reason) if reason else None,
                identifier,
            ),
        )


def attempts():
    with connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")]
