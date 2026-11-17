"""Source-only semantic index and bounded KG-guided selection for practice requests."""

import asyncio
import json
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from .evidence import EvidenceBundle, content_hash, digest, evidence_identities
from .semantic import LocalSemanticEncoder, sha256_file


def normalized(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


class BookIndex:
    def __init__(self, path, encoder_path, encoder=None):
        import numpy as np

        self.path = Path(path)
        self.manifest = json.loads((self.path / "index-manifest.json").read_text(encoding="utf-8"))
        for filename, key in (
            ("corpus.jsonl", "corpus_sha256"),
            ("vectors.npy", "vectors_sha256"),
            ("source-manifest.json", "source_manifest_sha256"),
        ):
            if sha256_file(self.path / filename) != self.manifest[key]:
                raise ValueError("RETRIEVAL_INDEX_HASH_MISMATCH")
        if (
            sha256_file(Path(encoder_path) / "manifest.json")
            != self.manifest["encoder_manifest_sha256"]
        ):
            raise ValueError("RETRIEVAL_ENCODER_VERSION_MISMATCH")
        self.corpus = [
            json.loads(line)
            for line in (self.path / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.vectors = np.load(self.path / "vectors.npy", allow_pickle=False)
        if self.vectors.shape != (len(self.corpus), self.manifest["dimensions"]):
            raise ValueError("RETRIEVAL_INDEX_SHAPE_MISMATCH")
        self.np = np
        self.encoder = encoder or LocalSemanticEncoder(encoder_path)
        self.pages = defaultdict(list)
        for i, c in enumerate(self.corpus):
            self.pages[(c["source_id"], c["page"])].append(i)

    def resolve(self, refs):
        supports = defaultdict(list)
        unresolved = []
        for ref in refs:
            excerpt = normalized(str(ref.get("excerpt", "")))
            indices = [
                i
                for page in ref.get("pdf_pages", [])
                for i in self.pages[(ref.get("source_id"), page)]
            ]
            found = [
                i for i in indices if excerpt and excerpt in normalized(self.corpus[i]["content"])
            ]
            if not found:
                # The full quoted source may cross a chunk boundary. Reconstruct its page.
                for page in ref.get("pdf_pages", []):
                    candidates = self.pages[(ref.get("source_id"), page)]
                    ordered = sorted(
                        (
                            self.corpus[i]
                            for i in candidates
                            if self.corpus[i].get("start") is not None
                        ),
                        key=lambda c: c["start"],
                    )
                    text = ""
                    for c in ordered:
                        start = c["start"]
                        if start <= len(text):
                            text += c["content"][max(0, len(text) - start) :]
                    if excerpt and excerpt in normalized(text):
                        found.extend(candidates)
            if found:
                for i in set(found):
                    supports[i].append(
                        {
                            k: ref.get(k)
                            for k in (
                                "source_id",
                                "locator_id",
                                "pdf_pages",
                                "node_ids",
                                "edge_id",
                                "condition",
                            )
                        }
                    )
            else:
                unresolved.append(
                    {
                        "source_id": ref.get("source_id"),
                        "locator_id": ref.get("locator_id"),
                        "reason": "source_reference_text_not_found",
                    }
                )
        return supports, unresolved

    def similarities(self, question):
        q = self.encoder.encode([question], query=True)[0]
        return self.vectors @ q


class PracticeBookRetriever:
    def __init__(
        self,
        index,
        graph,
        mapping,
        *,
        strategy="hybrid",
        min_similarity=0.75,
        top_k=3,
        context_chars=6000,
    ):
        self.index, self.graph = index, graph
        self.mapping = mapping
        self.strategy = strategy
        self.min_similarity = min_similarity
        self.top_k = top_k
        self.context_chars = context_chars

    async def retrieve(self, question_id, question, trace_id, *, source_ids=None):
        tick = time.perf_counter()
        mapping = self.mapping.get("questions", {}).get(question_id)
        concept_ids = []
        reason = None
        if mapping:
            if content_hash(question) != mapping["question_sha256"]:
                raise ValueError("QUESTION_CONCEPT_MAPPING_VERSION_MISMATCH")
            concept_ids = mapping["concept_ids"][:3]
        else:
            reason = "no_curated_concept_mapping"
        trace = {
            "trace_id": trace_id,
            "question_id": question_id,
            "question_sha256": content_hash(question),
            "requested_strategy": self.strategy,
            "effective_strategy": "vector",
            "data_source": "source_corpus_snapshot",
            "mapping_version": self.mapping["version"],
            "concept_ids": concept_ids,
            "kg_node_ids": [],
            "kg_edges": [],
            "kg_candidate_count": 0,
            "neo4j_queries": 0,
            "vector_search": True,
            "vector_queries": 1,
            "encoder": self.index.manifest["encoder"],
            "corpus_sha256": self.index.manifest["corpus_sha256"],
            "kg_contributed": False,
            "max_hops": 1,
            "top_k": self.top_k,
            "context_char_limit": self.context_chars,
            "fallback_reason": reason,
            "adequacy": "source_candidates_not_clinically_adjudicated",
        }
        source_ids = mapping.get("source_ids", []) if mapping else (source_ids or [])
        trace["allowed_source_ids"] = source_ids
        if not source_ids:
            trace.update(
                effective_strategy="none",
                status="insufficient_evidence",
                selected_evidence=[],
                candidate_count=0,
                vector_search=False,
                vector_queries=0,
                fallback_reason="unverified_source_scope",
                retrieval_seconds=time.perf_counter() - tick,
            )
            return EvidenceBundle([], [], trace)
        scores = await asyncio.to_thread(self.index.similarities, question)
        eligible = [
            i
            for i in self.index.np.flatnonzero(scores >= self.min_similarity).tolist()
            if not source_ids or self.index.corpus[i]["source_id"] in source_ids
        ]
        supports = {}
        if self.strategy in {"hybrid", "kg_lookup"}:
            kg = await self.graph.lookup(concept_ids)
            trace.update(
                kg_data_source=kg.source,
                neo4j_queries=kg.requests,
                kg_node_ids=[n["id"] for n in kg.nodes],
                kg_nodes=[
                    {"id": n["id"], "content_sha256": digest(n.get("content", []))}
                    for n in kg.nodes
                ],
                kg_edges=[
                    {k: e.get(k) for k in ("id", "type", "from_id", "to_id", "condition")}
                    for e in kg.edges
                ],
            )
            try:
                supports, unresolved = self.index.resolve(kg.references())
            except (ValueError, TypeError, KeyError):
                supports, unresolved = {}, [{"reason": "kg_provenance_unreadable"}]
            trace["unresolved_references"] = unresolved
            trace["kg_candidate_count"] = len(supports)
            trace["kg_candidates"] = [
                {"source_unit_id": self.index.corpus[i]["source_unit_id"], "supports": refs}
                for i, refs in sorted(supports.items())
            ][:40]
            if kg.error:
                trace["fallback_reason"] = kg.error
            elif not kg.nodes:
                trace["fallback_reason"] = (
                    "no_curated_concept_mapping" if not concept_ids else "kg_concepts_not_found"
                )
            elif not supports:
                trace["fallback_reason"] = (
                    "kg_evidence_not_resolvable"
                    if unresolved
                    else "kg_concept_has_no_source_evidence"
                )
            if self.strategy == "kg_lookup":
                eligible = [i for i in supports if i in eligible]
            elif supports:
                vector_top = sorted(eligible, key=lambda i: (-float(scores[i]), i))[:20]
                eligible = sorted(set(vector_top) | {i for i in supports if i in eligible})
        ranked = sorted(
            eligible,
            key=lambda i: (
                -(
                    0.85 * float(scores[i]) + 0.15 * bool(supports.get(i))
                    if supports
                    else float(scores[i])
                ),
                i,
            ),
        )
        evidence, provenance = [], []
        used = 0
        selected_kg = False
        selected_rows = []
        for i in ranked:
            c = self.index.corpus[i]
            if used + len(c["content"]) > self.context_chars:
                continue  # Never cut a source quote to meet the prompt budget.
            if any(
                e["source_id"] == c["source_id"] and e["content"] == c["content"] for e in evidence
            ):
                continue
            entry = {
                "source_unit_id": c["source_unit_id"],
                "source_id": c["source_id"],
                "title": c["chapter"] or "Source text",
                "page_start": c["page"],
                "page_end": c["page"],
                "content": c["content"],
            }
            evidence.append(entry)
            used += len(c["content"])
            kg_support = supports.get(i, [])
            selected_kg |= bool(kg_support)
            provenance.append(
                {
                    "source_unit_id": entry["source_unit_id"],
                    "source_id": c["source_id"],
                    "sha256": c.get("book_sha256"),
                    "pdf_page_start": c["page"],
                    "pdf_page_end": c["page"],
                    "source_version_sha256": c.get("source_version_sha256"),
                    "book_year": c.get("book_year"),
                    "source_char_start": c.get("start"),
                    "source_char_end": c.get("end"),
                    "content_sha256": content_hash(c["content"]),
                    "origin": c["origin"],
                    "kg_support": kg_support,
                    "review_status": "source_checked_draft",
                    "expert_verified": False,
                }
            )
            selected_rows.append(
                {
                    **evidence_identities([entry])[0],
                    "rank": len(evidence),
                    "semantic_score": float(scores[i]),
                    "combined_score": (0.85 * float(scores[i]) + 0.15 * bool(kg_support))
                    if supports
                    else float(scores[i]),
                    "kg_supported": bool(kg_support),
                }
            )
            if len(evidence) == self.top_k:
                break
        trace.update(
            candidate_count=len(ranked),
            selected_evidence=evidence_identities(evidence),
            ranking=selected_rows,
            kg_contributed=selected_kg,
            status="retrieved_unadjudicated" if evidence else "insufficient_evidence",
        )
        if self.strategy == "kg_lookup":
            trace["effective_strategy"] = "kg_lookup" if selected_kg else "none"
        elif self.strategy == "hybrid" and selected_kg:
            trace["effective_strategy"] = "hybrid"
            trace["fallback_reason"] = None
        elif self.strategy == "hybrid" and supports and not selected_kg:
            trace["fallback_reason"] = "kg_candidates_not_selected"
        if not evidence and not trace["fallback_reason"]:
            trace["fallback_reason"] = "no_relevant_source_candidates"
        if selected_kg:
            trace["data_source"] = trace["kg_data_source"] + "+source_corpus_snapshot"
        if getattr(self.graph, "snapshot_sha256", None):
            trace["kg_snapshot_sha256"] = self.graph.snapshot_sha256
        trace["retrieval_seconds"] = time.perf_counter() - tick
        return EvidenceBundle(evidence, provenance, trace)
