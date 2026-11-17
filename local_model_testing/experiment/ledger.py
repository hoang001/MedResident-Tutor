"""One durable attempt budget for the whole experiment, across CLI invocations."""
import sqlite3
from datetime import UTC, datetime

from .common import DATA, RUN, read


def connect():
    RUN.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(RUN / "execution-ledger.sqlite3", timeout=30)
    db.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, config TEXT, "
               "sample_id TEXT, category TEXT, fingerprint TEXT, started TEXT, finished TEXT, "
               "status TEXT, generation_started INTEGER DEFAULT 0, reason TEXT)")
    return db


def reserve(config, sample_id, category, fp):
    budget = read(DATA / "experiment.json")["budgets"]
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        total = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM attempts WHERE category=?", (category,)).fetchone()[0]
        if total >= budget["total"] or count >= budget[category]:
            raise RuntimeError("EXPERIMENT_ATTEMPT_BUDGET_EXHAUSTED")
        prior = db.execute("SELECT id FROM attempts WHERE config=? AND sample_id=?",
                           (config, sample_id)).fetchone()
        if prior:
            raise RuntimeError("PREVIOUS_ATTEMPT_EXISTS; no silent retry")
        cur = db.execute("INSERT INTO attempts(config,sample_id,category,fingerprint,started,status) "
                         "VALUES (?,?,?,?,?,'started')", (config, sample_id, category, fp,
                                                          datetime.now(UTC).isoformat()))
        return cur.lastrowid


def generation_started(attempt):
    with connect() as db:
        db.execute("UPDATE attempts SET generation_started=1 WHERE id=?", (attempt,))


def finish(attempt, status, reason=None):
    with connect() as db:
        db.execute("UPDATE attempts SET finished=?, status=?, reason=? WHERE id=?",
                   (datetime.now(UTC).isoformat(), status, reason, attempt))


def report():
    with connect() as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")]
