"""Logic-only tests: fake vectors/graph are explicitly not evidence of live retrieval."""

import json

import numpy as np
import pytest

from app.ai.retrieval.books import BookIndex, PracticeBookRetriever
from app.ai.retrieval.evidence import (
    content_hash,
    evidence_identities,
    prelinked_trace,
    verify_payload_evidence,
)
from app.ai.retrieval.graph import GraphCandidates, SnapshotEvidenceRepository


class FakeIndex:
    np = np
    manifest = {"encoder": {"test_fake": True}, "corpus_sha256": "sourcehash"}
    corpus = [
        {
            "source_unit_id": "S1",
            "source_id": "BOOK",
            "page": 9,
            "chapter": "Heading",
            "content": "The complete source condition and exception.",
            "origin": "test_fake",
            "start": 0,
            "end": 44,
            "book_sha256": "a" * 64,
        }
    ]

    def __init__(self, score=0.9):
        self.score = score
        self.queries = []

    def similarities(self, question):
        self.queries.append(question)
        return np.array([self.score])

    def resolve(self, refs):
        return ({0: list(refs)} if refs else {}), []


class FakeGraph:
    def __init__(self, error=None, sources=True):
        self.error = error
        self.sources = sources
        self.calls = 0

    async def lookup(self, ids):
        if not ids:
            return GraphCandidates("live_neo4j")
        self.calls += 1
        return GraphCandidates(
            "live_neo4j",
            nodes=[]
            if self.error
            else [
                {
                    "id": "N1",
                    "content": [
                        {
                            "sources": [
                                {"source_id": "BOOK", "pdf_pages": [9], "excerpt": "condition"}
                            ]
                        }
                    ]
                    if self.sources
                    else [],
                }
            ],
            requests=1,
            error=self.error,
        )


def retriever(strategy="hybrid", score=0.9, error=None, sources=True):
    index = FakeIndex(score)
    graph = FakeGraph(error, sources)
    mapping = {
        "version": "test_only",
        "questions": {
            "Q": {
                "question_sha256": content_hash("QUESTION"),
                "concept_ids": ["N1"],
                "source_ids": ["BOOK"],
            }
        },
    }
    return PracticeBookRetriever(index, graph, mapping, strategy=strategy)


def test_evidence_hash_chain_rejects_mutated_text():
    evidence = [
        {
            "source_unit_id": "S",
            "source_id": "B",
            "page_start": 1,
            "page_end": 1,
            "content": "not allowed",
        }
    ]
    trace = prelinked_trace(evidence, "trace")
    verify_payload_evidence({"evidence": evidence}, trace)
    changed = [{**evidence[0], "content": "allowed"}]
    with pytest.raises(ValueError, match="RETRIEVAL_PAYLOAD_EVIDENCE_MISMATCH"):
        verify_payload_evidence({"evidence": changed}, trace)


@pytest.mark.asyncio
async def test_vector_never_queries_kg_or_accepts_answer_or_rubric():
    r = retriever("vector")
    bundle = await r.retrieve("Q", "QUESTION", "T")
    assert r.index.queries == ["QUESTION"] and r.graph.calls == 0
    assert bundle.trace["effective_strategy"] == "vector"
    assert bundle.trace["selected_evidence"] == evidence_identities(bundle.evidence)
    assert bundle.trace["adequacy"] != "sufficient"


@pytest.mark.asyncio
async def test_hybrid_uses_provenance_candidates_and_keeps_whole_text():
    r = retriever()
    b = await r.retrieve("Q", "QUESTION", "T")
    assert b.trace["effective_strategy"] == "hybrid" and b.trace["kg_contributed"]
    assert b.evidence[0]["content"] == r.index.corpus[0]["content"]
    assert b.provenance[0]["kg_support"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,sources,reason",
    [
        ("TEST_CONNECTION_ERROR", True, "TEST_CONNECTION_ERROR"),
        (None, False, "kg_concept_has_no_source_evidence"),
    ],
)
async def test_kg_failure_is_labelled_vector_fallback(error, sources, reason):
    b = await retriever(error=error, sources=sources).retrieve("Q", "QUESTION", "T")
    assert b.trace["effective_strategy"] == "vector" and not b.trace["kg_contributed"]
    assert b.trace["fallback_reason"] == reason
    assert b.trace["data_source"] == "source_corpus_snapshot"


@pytest.mark.asyncio
async def test_low_relevance_is_insufficient_not_a_topk_success():
    b = await retriever("vector", score=0.1).retrieve("Q", "QUESTION", "T")
    assert not b.evidence and b.trace["status"] == "insufficient_evidence"


@pytest.mark.asyncio
async def test_unmapped_unscoped_request_does_not_search_or_call_kg():
    r = retriever()
    b = await r.retrieve("UNKNOWN", "QUESTION", "T")
    assert b.trace["status"] == "insufficient_evidence" and not b.evidence
    assert not r.index.queries and not r.graph.calls


@pytest.mark.asyncio
async def test_unmapped_but_verified_book_scope_can_fallback_to_vector():
    r = retriever()
    b = await r.retrieve("UNKNOWN", "QUESTION", "T", source_ids=["BOOK"])
    assert b.trace["effective_strategy"] == "vector" and b.evidence
    assert b.trace["fallback_reason"] == "no_curated_concept_mapping"


@pytest.mark.asyncio
async def test_mapping_hash_refuses_reused_question_id():
    with pytest.raises(ValueError, match="MAPPING_VERSION_MISMATCH"):
        await retriever().retrieve("Q", "DIFFERENT QUESTION", "T")


@pytest.mark.asyncio
async def test_offline_snapshot_is_one_hop_and_keeps_edge_condition(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(
        json.dumps(
            {
                "nodes": [{"id": n} for n in "ABC"],
                "edges": [
                    {
                        "id": "E1",
                        "from_id": "A",
                        "to_id": "B",
                        "type": "IS_A",
                        "condition": "only if X",
                        "sources": [],
                    },
                    {
                        "id": "E2",
                        "from_id": "B",
                        "to_id": "C",
                        "type": "IS_A",
                        "condition": None,
                        "sources": [],
                    },
                ],
            }
        )
    )
    repo = SnapshotEvidenceRepository(path)
    result = await repo.lookup(["A"])
    assert {n["id"] for n in result.nodes} == {"A", "B"}
    assert result.edges[0]["condition"] == "only if X"
    assert result.source == "offline_graph_snapshot" and result.requests == 0


def test_unreadable_source_reference_never_becomes_evidence():
    index = object.__new__(BookIndex)
    index.pages = {}
    from collections import defaultdict

    index.pages = defaultdict(list)
    index.corpus = []
    supports, unresolved = index.resolve(
        [{"source_id": "B", "pdf_pages": [999], "excerpt": "not present"}]
    )
    assert not supports and unresolved[0]["reason"] == "source_reference_text_not_found"
