"""Build a source-only corpus/index on CPU before any Medical request."""

import argparse
import json
import sys
import time
from collections import defaultdict

from .common import ROOT, CORPUS, ENCODER, read, rows, jsonl, write, file_hash, digest


def build_corpus():
    original = rows(ROOT / "data/evaluation/medresident-benchmark-v1/corpus.jsonl")
    graph_paths = [
        ROOT
        / "data/knowledge-extraction/v2/source-review-20261102/combined/graph.json",
        ROOT
        / "data/knowledge-extraction/v2/source-review-20261102-2021-completion/combined/graph.json",
    ]
    references = defaultdict(set)
    for p in graph_paths:
        g = read(p)
        for item in g["nodes"] + g["edges"]:
            refs = list(item.get("sources", []))
            for block in item.get("content", []):
                refs.extend(block.get("sources", []))
            for ref in refs:
                for page in ref["pdf_pages"]:
                    references[(ref["source_id"], page)].add(
                        " ".join(ref["excerpt"].split())
                    )
    pages = defaultdict(list)
    audit_files = []
    for root in [p.parent.parent for p in graph_paths]:
        for p in sorted(root.rglob("pages.jsonl")):
            if "history" in p.parts:
                continue
            audit_files.append(p)
            for row in rows(p):
                key = (row["source_id"], row["pdf_page"])
                normalized = " ".join(row["text"].split())
                matches = sum(excerpt in normalized for excerpt in references[key])
                pages[key].append((matches, str(p), row))
    corpus = [c for c in original if (c["source_id"], c["page"]) not in pages]
    for key, alternatives in sorted(pages.items()):
        # Choose the already-reviewed page version matching most accepted graph citations.
        # This is source identity resolution, before retrieval/model evaluation.
        _, path, page = max(alternatives, key=lambda x: (x[0], x[1]))
        text = page["text"]
        revision = digest(text)
        for start in range(0, len(text), 1400):
            content = text[start : start + 1800]
            if not content.strip():
                continue
            corpus.append(
                {
                    "chunk_id": f"REVIEW_{key[0]}_{key[1]}_{start}_{revision[:8]}",
                    "source_id": key[0],
                    "page": key[1],
                    "start": start,
                    "end": start + len(content),
                    "content": content,
                    "chapter": "",
                    "origin": "source_reviewed_page",
                    "source_version_sha256": revision,
                    "ocr_sha256": page["ocr_sha256"],
                    "source_artifact": str(ROOT / path)
                    .replace(str(ROOT) + "/", "")
                    .replace("\\", "/"),
                    "document_edition_id": page["document_edition_id"],
                }
            )
            if start + 1800 >= len(text):
                break
    catalog = read(ROOT / "data/library/catalog.json")
    for c in corpus:
        book = next(b for b in catalog["books"] if b["id"] == c["source_id"])
        c["book_sha256"] = book["sha256"]
        c["book_year"] = book["year"]
        c["chapter"] = next(
            (
                ch["title"]
                for ch in book["chapters"]
                if ch["start"] <= c["page"] <= ch["end"]
            ),
            "",
        )
        c["source_unit_id"] = (
            "RB1_"
            + digest(
                {k: c.get(k) for k in ("source_id", "page", "start", "end", "content")}
            )[:32]
        )
    jsonl(CORPUS / "corpus.jsonl", corpus)
    write(
        CORPUS / "source-manifest.json",
        {
            "corpus_sha256": file_hash(CORPUS / "corpus.jsonl"),
            "catalog_sha256": file_hash(CORPUS / "catalog.json"),
            "chunks": len(corpus),
            "reviewed_pages": len(pages),
            "source_audit_files": {
                p.relative_to(ROOT).as_posix(): file_hash(p) for p in audit_files
            },
            "graph_source_files": {
                p.relative_to(ROOT).as_posix(): file_hash(p) for p in graph_paths
            },
            "content_policy": "Full source page windows, original OCR or existing reviewed page revision; no answers, questions, expected or new LLM/OCR",
        },
    )
    print(
        json.dumps({"source_chunks": len(corpus), "reviewed_pages": len(pages)}),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-only", action="store_true")
    args = parser.parse_args()
    if (CORPUS / "index-manifest.json").exists():
        saved = read(CORPUS / "index-manifest.json")
        assert file_hash(CORPUS / "corpus.jsonl") == saved["corpus_sha256"]
        assert file_hash(CORPUS / "vectors.npy") == saved["vectors_sha256"]
        print(
            "Existing source index verified/reused; no overwrite or model generation",
            flush=True,
        )
        return
    if not (CORPUS / "index-manifest.json").exists():
        build_corpus()
    if args.corpus_only:
        return
    sys.path.insert(0, str(ROOT / "apps/backend"))
    from app.ai.retrieval.semantic import LocalSemanticEncoder
    import numpy as np

    corpus = rows(CORPUS / "corpus.jsonl")
    encoder = LocalSemanticEncoder(ENCODER)
    start = time.perf_counter()

    def progress(n, total):
        if n % 120 == 0 or n == total:
            print(
                json.dumps({"encoded_windows": n, "total_windows": total}), flush=True
            )

    vectors = encoder.encode(
        [c["chapter"] + "\n" + c["content"] for c in corpus], progress=progress
    )
    np.save(CORPUS / "vectors.npy", vectors, allow_pickle=False)
    write(
        CORPUS / "index-manifest.json",
        {
            "source_manifest_sha256": file_hash(CORPUS / "source-manifest.json"),
            "corpus_sha256": file_hash(CORPUS / "corpus.jsonl"),
            "vectors_sha256": file_hash(CORPUS / "vectors.npy"),
            "encoder": encoder.identity,
            "encoder_manifest_sha256": file_hash(ENCODER / "manifest.json"),
            "rows": len(corpus),
            "dimensions": vectors.shape[1],
            "index_seconds": time.perf_counter() - start,
            "medical_generations": 0,
            "runtime": "local CPU, encoder only",
        },
    )
    print("Source semantic index ready; zero generative requests", flush=True)


if __name__ == "__main__":
    main()
