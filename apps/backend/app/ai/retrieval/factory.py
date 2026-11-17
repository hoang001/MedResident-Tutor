"""Opt-in practice retrieval. The ordinary web default remains prelinked."""

import json
from functools import lru_cache
from pathlib import Path

from .books import BookIndex, PracticeBookRetriever
from .graph import Neo4jEvidenceRepository, SnapshotEvidenceRepository


@lru_cache(maxsize=2)
def book_index(corpus, encoder):
    return BookIndex(corpus, encoder)


def mapping(settings):
    return json.loads(Path(settings.practice_retrieval_mapping).read_text(encoding="utf-8"))


def is_textbook_question(question, settings):
    fields = (question.import_metadata or {}).get("dataset_fields", {})
    if fields.get("clinical_exercise"):
        return False
    if fields.get("retrieval_scope") == "textbook":
        return True
    return question.external_id in mapping(settings)["questions"]


def create_retriever(settings):
    index = book_index(
        str(settings.practice_retrieval_corpus), str(settings.practice_retrieval_encoder)
    )
    graph = (
        Neo4jEvidenceRepository(settings)
        if settings.practice_retrieval_graph == "neo4j"
        else SnapshotEvidenceRepository(settings.practice_retrieval_snapshot)
    )
    return PracticeBookRetriever(
        index,
        graph,
        mapping(settings),
        strategy=settings.practice_retrieval_strategy,
        min_similarity=settings.practice_retrieval_min_similarity,
    )
