"""Question-specific lexical reranking for authoring only; grading retrieval is unchanged."""

import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache

STOP = set(
    (
        "theo neu cac nhung nao gi vi sao can trong duoc mo ta tai lieu "
        "cua va la ve de cho do nay hay nam"
    ).split()
)


def terms(text):
    normalized = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    words = [word for word in re.findall(r"[^\W_]+", normalized) if not word.isdecimal()]
    result = [word for word in words if word not in STOP]
    result += [
        a + " " + b
        for a, b in zip(words, words[1:], strict=False)
        if a not in STOP and b not in STOP
    ]
    return result


@lru_cache(maxsize=2)
def lexical_documents(index):
    documents = [Counter(terms(row["content"])) for row in index.corpus]
    frequencies = Counter(term for doc in documents for term in doc)
    lengths = [sum(doc.values()) for doc in documents]
    return documents, frequencies, lengths, sum(lengths) / max(1, len(lengths))


class AuthoringIndex:
    """Same verified source corpus/encoder with an inspectable authoring relevance score."""

    def __init__(self, index, min_similarity, source_ids=None):
        self.base = index
        self.corpus, self.manifest, self.np = index.corpus, index.manifest, index.np
        self.min_similarity = min_similarity
        self.source_ids = set(source_ids or [])
        self.semantic = self.lexical = None

    def resolve(self, refs):
        return self.base.resolve(refs)

    def similarities(self, question):
        self.semantic = self.base.similarities(question)
        # A bibliographic preamble describes scope, not the knowledge being asked.
        query = re.sub(r"^\s*theo\b.*?\(\s*\d{4}\s*\)\s*[,;:]?", "", question, flags=re.I)
        query_terms = Counter(terms(query))
        documents, frequencies, lengths, average = lexical_documents(self.base)
        count = len(documents)
        lexical = []
        for doc, length in zip(documents, lengths, strict=True):
            score = 0.0
            for term, query_count in query_terms.items():
                frequency = doc[term]
                if not frequency:
                    continue
                inverse = math.log(
                    1 + (count - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                )
                saturation = (
                    frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / max(average, 1)))
                )
                score += inverse * saturation * (1 + math.log(query_count))
            lexical.append(score)
        eligible = self.semantic >= self.min_similarity
        if self.source_ids:
            eligible &= self.np.array([row["source_id"] in self.source_ids for row in self.corpus])
        maximum = max(
            (score for score, allowed in zip(lexical, eligible, strict=True) if allowed), default=0
        )
        self.lexical = self.np.array(lexical) / maximum if maximum else self.np.zeros(count)
        relevance = self.semantic.copy()
        # Preserve the semantic eligibility gate. Lexical matching cannot promote
        # a semantically rejected passage or bypass the allowed source scope.
        relevance[eligible] += 0.5 * self.lexical[eligible]
        return relevance

    def annotate(self, trace):
        indices = {row["source_unit_id"]: i for i, row in enumerate(self.corpus)}
        for row in trace.get("ranking", []):
            i = indices[row["source_unit_id"]]
            row["authoring_relevance_score"] = row["semantic_score"]
            row["semantic_score"] = float(self.semantic[i])
            row["lexical_score"] = float(self.lexical[i])
        trace["authoring_reranker"] = {
            "version": "authoring-lexical-v1",
            "lexical_weight": 0.5,
            "semantic_eligibility_preserved": True,
            "combined_score_is_probability": False,
        }
