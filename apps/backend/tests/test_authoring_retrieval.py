import numpy as np

from app.ai.retrieval.authoring import AuthoringIndex


class Index:
    np = np
    manifest = {}
    corpus = [
        {"source_unit_id": "general", "content": "Alpha condition treatment and diagnosis."},
        {
            "source_unit_id": "answer",
            "content": "Alpha condition affects the delta nerve through pressure.",
        },
        {"source_unit_id": "irrelevant", "content": "Which nerve is affected in alpha condition?"},
    ]

    def similarities(self, question):
        return np.array([0.94, 0.88, 0.2])


def test_authoring_focuses_question_terms_without_promoting_below_threshold():
    index = AuthoringIndex(Index(), 0.75)
    scores = index.similarities("Which nerve is affected in alpha condition?")
    assert scores[1] > scores[0]
    assert scores[2] == 0.2
    trace = {"ranking": [{"source_unit_id": "answer", "semantic_score": float(scores[1])}]}
    index.annotate(trace)
    assert trace["ranking"][0]["semantic_score"] == 0.88
    assert trace["ranking"][0]["lexical_score"] > 0
    assert trace["authoring_reranker"]["semantic_eligibility_preserved"]


def test_no_lexical_match_keeps_original_semantics():
    index = AuthoringIndex(Index(), 0.75)
    assert np.array_equal(index.similarities("unrelated zebra"), [0.94, 0.88, 0.2])


def test_lexical_terms_match_vietnamese_without_diacritics():
    from app.ai.retrieval.authoring import terms

    assert "than kinh" in terms("Thần kinh giữa")
    assert "than kinh" in terms("than kinh")


def test_source_scope_is_preserved_when_normalizing_lexical_scores():
    base = Index()
    base.corpus = [
        {**row, "source_id": "allowed" if i == 0 else "excluded"}
        for i, row in enumerate(base.corpus)
    ]
    index = AuthoringIndex(base, 0.75, ["allowed"])
    scores = index.similarities("Which nerve is affected in alpha condition?")
    assert scores[0] == 0.94 + 0.5
    assert scores[1] == 0.88
    assert scores[2] == 0.2
