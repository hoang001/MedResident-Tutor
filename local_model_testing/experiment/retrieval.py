"""Offline lexical-vector/KG ablation; never calls the app, Neo4j, or any LLM."""
import json
import time
from collections import defaultdict

from .common import DATA, RUN, frozen, read, rows, write


class OfflineRetriever:
    def __init__(self, corpus, graph):
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.np = np
        self.corpus = corpus
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
            min_df=2, max_features=80000, norm="l2", sublinear_tf=True, dtype=np.float32)
        self.vectors = self.vectorizer.fit_transform([c["content"] for c in corpus])
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.node_ids = sorted(self.nodes)
        self.node_vectors = self.vectorizer.transform([
            " ".join([self.nodes[n].get("name", ""), *(self.nodes[n].get("aliases") or [])])
            for n in self.node_ids])
        self.neighbors = defaultdict(set)
        for e in graph["edges"]:
            self.neighbors[e["from_id"]].add(e["to_id"])
            self.neighbors[e["to_id"]].add(e["from_id"])

    def rank(self, question, hybrid=False):
        # This API intentionally accepts no gold IDs, rubric, expected or student answer.
        q = self.vectorizer.transform([question])
        scores = (self.vectors @ q.T).toarray().ravel()
        seeds = []
        if hybrid:
            affinity = (self.node_vectors @ q.T).toarray().ravel()
            page_boost = defaultdict(float)
            for index in self.np.argsort(-affinity)[:3]:
                confidence = float(affinity[index])
                if confidence < .15:
                    continue
                node_id = self.node_ids[index]
                seeds.append(node_id)
                related = [(node_id, confidence)] + [(n, confidence*.5)
                    for n in sorted(self.neighbors[node_id]) if n in self.nodes]
                for nid, value in related:
                    for content in self.nodes[nid].get("content", []):
                        for source in content.get("sources", []):
                            for page in source.get("pdf_pages", []):
                                key = (source["source_id"], page)
                                page_boost[key] = max(page_boost[key], value)
            scores = .85*scores + .15*self.np.array([
                page_boost[(c["source_id"], c["page"])] for c in self.corpus])
        selected, used = [], 0
        for index in self.np.argsort(-scores, kind="stable"):
            chunk = dict(self.corpus[index])
            # Deduplicate identical same-source text. Keep partially overlapping spans;
            # evaluator merges their coverage, so overlap cannot inflate evidence recall.
            if any(c["source_id"] == chunk["source_id"] and c["content"] == chunk["content"] for c in selected):
                continue
            remaining = 6000-used
            if remaining <= 0 or len(selected) == 5:
                break
            chunk["content"] = chunk["content"][:remaining]
            if chunk["start"] is not None:
                chunk["end"] = chunk["start"] + len(chunk["content"])
            chunk["score"] = float(scores[index])
            selected.append(chunk)
            used += len(chunk["content"])
        return selected, seeds


def covered_length(intervals):
    length, end = 0, None
    for left, right in sorted(intervals):
        if right <= left:
            continue
        if end is None or left > end:
            length += right-left
        elif right > end:
            length += right-end
        end = max(end or right, right)
    return length


def coverage(retrieved, provenance):
    relevant = [c for c in retrieved if c["source_id"] == provenance["source_id"]
                and c["page"] == provenance["pdf_page"]]
    start, end = provenance["source_window_start"], provenance["source_window_end"]
    if start is None:
        target = " ".join(provenance["original_excerpt"].split()).casefold()
        full = any(target in " ".join(c["content"].split()).casefold() for c in relevant)
        return {"hit_at_5": full, "strict_source_span_coverage": 1.0 if full else 0.0}
    intervals = [(max(start, c["start"]), min(end, c["end"])) for c in relevant if c["start"] is not None]
    fraction = min(1.0, covered_length(intervals)/(end-start))
    single_hit = any(max(0, right-left)/(end-start) >= .5 for left, right in intervals)
    return {"hit_at_5": single_hit, "strict_source_span_coverage": fraction}


def main():
    import importlib.metadata
    import numpy as np

    frozen()
    corpus, graph = rows(DATA / "corpus.jsonl"), read(DATA / "graph-snapshot.json")
    start = time.perf_counter()
    retriever = OfflineRetriever(corpus, graph)
    build_seconds = time.perf_counter()-start
    provenance = {r["question_id"]: r for r in rows(DATA / "provenance.jsonl")}
    records, aggregate = [], {}
    for mode in ("vector", "hybrid"):
        for q in rows(DATA / "questions.jsonl"):
            tick = time.perf_counter()
            found, seeds = retriever.rank(q["question"], hybrid=mode == "hybrid")
            elapsed = time.perf_counter()-tick
            cov = coverage(found, provenance[q["question_id"]])
            all_source = cov["strict_source_span_coverage"] >= 1-1e-9
            records.append({"mode": mode, "question_id": q["question_id"], "topic": q["topic"],
                "latency_seconds": elapsed, **cov,
                "criterion_evidence_coverage_proxy": float(all_source),
                "semantic_criterion_coverage": None,
                "retrieved_chunk_ids": [c["chunk_id"] for c in found], "linked_seed_nodes": seeds,
                "retrieved": found})
        group = [r for r in records if r["mode"] == mode]
        aggregate[mode] = {"queries": len(group), "hit_at_5": np.mean([r["hit_at_5"] for r in group]).item(),
            "criterion_evidence_coverage_proxy": np.mean([r["criterion_evidence_coverage_proxy"] for r in group]).item(),
            "semantic_criterion_coverage": None,
            "latency_median_seconds": float(np.median([r["latency_seconds"] for r in group])),
            "latency_p95_seconds": float(np.percentile([r["latency_seconds"] for r in group], 95))}
    configuration = {"scope": "offline, not live Neo4j retrieval", "corpus_chunks": len(corpus),
        "embedding": "corpus-only character TF-IDF char_wb 3..5, 80000 maximum features; sparse lexical vector, not neural embeddings",
        "same_embedding_and_context_for_both": True, "top_k": 5, "context_char_limit": 6000,
        "hybrid": "0.85 cosine + 0.15 source-page support from three linked KG nodes and one-hop neighbors",
        "reranker": None, "build_seconds": build_seconds,
        "hit_policy": "At least one top5 chunk overlaps >=50% of agent-selected source passage; same source/page; manually transcribed equivalent units accepted",
        "coverage_policy": "Conservative complete selected source-passage coverage for each rubric criterion; same passage supports both criteria; overlapping spans merged, never double-counted",
        "clinical_semantic_relevance_labels": "Unavailable: semantic criterion coverage N/A; proxy is not expert relevance adjudication",
        "packages": {p: importlib.metadata.version(p) for p in ("scikit-learn", "numpy", "scipy")}}
    write(RUN / "retrieval.json", {"configuration": configuration, "metrics": aggregate, "records": records})
    print(json.dumps({"scope": "offline lexical-vector/KG ablation", "metrics": aggregate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
