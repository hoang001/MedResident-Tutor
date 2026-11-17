"""Source-scoped self-study questions from KG; no generation model or grading.

Prompts are templates, not book quotations. Source statements stay separate by
book/year. No clinical case, diagnosis, scoring rubric or canonical fact is invented.
"""

import hashlib
import json
import re

from app.modules.knowledge.service import folded

VERSION = "kg-self-study-v1"
TASKS = {
    "Condition": "Trình bày nội dung nguồn về",
    "Anatomy": "Mô tả các đặc điểm giải phẫu được nguồn nêu về",
    "Finding": "Mô tả dấu hiệu được nguồn nêu về",
    "Classification": "Trình bày cách phân loại được nguồn mô tả về",
    "ClassificationCategory": "Nêu các tiêu chí và điều kiện của nhóm",
    "DiagnosticMethod": "Trình bày phương pháp và điều kiện áp dụng được nguồn nêu về",
    "Intervention": "Trình bày nội dung can thiệp và các điều kiện được nguồn nêu về",
    "ClinicalPrinciple": "Giải thích nguyên tắc được nguồn nêu về",
    "Skill": "Trình bày các bước hoặc yêu cầu được nguồn nêu về",
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def usable_ref(ref, book):
    pages = ref.get("pdf_pages", [])
    return (
        bool(str(ref.get("excerpt", "")).strip())
        and bool(pages)
        and all(type(p) is int and 1 <= p <= book["pages"] for p in pages)
        and bool(re.fullmatch(r"[a-f0-9]{64}", book.get("sha256", "")))
    )


def chapters_for(refs, book):
    pages = {p for r in refs for p in r["pdf_pages"]}
    return [
        {"source_id": book["id"], "number": c["number"]}
        for c in book["chapters"]
        if any(c["start"] <= p <= c["end"] for p in pages)
    ]


def sourced_refs(refs, books):
    grouped = {}
    for ref in refs:
        book = books.get(ref.get("source_id"))
        if book and usable_ref(ref, book):
            grouped.setdefault(book["id"], {})[fingerprint(ref)] = ref
    return {book: [rows[k] for k in sorted(rows)] for book, rows in grouped.items()}


def question_bank(snapshot):
    bank = {}
    for node in sorted(snapshot.nodes.values(), key=lambda n: n["id"]):
        if node["type"] == "SampleQuestion":
            related = {
                n
                for e in snapshot.edges
                if node["id"] in (e["start"], e["end"])
                for n in (e["start"], e["end"])
                if not snapshot.nodes[n]["curricular"]
            }
            bank[node["id"]] = {
                k: node[k] for k in ("id", "title", "sources", "book_ids", "chapters", "revision")
            } | {
                "origin": "book",
                "task": "source_question",
                "node_ids": sorted(related | {node["id"]}),
                "review_status": node["review_status"],
                "expert_verified": False,
            }
            continue
        if node["curricular"] or node["type"] not in TASKS:
            continue
        # A node may aggregate books: question bases are split by book, never fused.
        grouped = {}
        for block in node["content"]:
            if not block["text"].strip():
                continue
            for book_id, refs in sourced_refs(block["sources"], snapshot.books).items():
                grouped.setdefault(book_id, []).append({"text": block["text"], "sources": refs})
        for book_id, blocks in grouped.items():
            unique = {fingerprint(b): b for b in blocks}
            blocks = [unique[k] for k in sorted(unique)]
            # Do not truncate conditions or claim broad coverage on oversized concepts.
            if sum(len(b["text"]) for b in blocks) > 12000:
                continue
            book = snapshot.books[book_id]
            refs = sourced_refs([r for b in blocks for r in b["sources"]], snapshot.books)[book_id]
            prompt = (
                f"Theo {book['title']} ({book.get('year', 'không rõ năm')}), "
                f"{TASKS[node['type']].lower()} “{node['title']}” trong phạm vi trang được dẫn. "
                "Giữ các điều kiện và ngoại lệ nếu nguồn có nêu."
            )
            add_question(bank, [node], book, refs, prompt, blocks, "source_recall")
    # Only explicit clinical relationships with their own source support qualify.
    for edge in snapshot.edges:
        left, right = snapshot.nodes[edge["start"]], snapshot.nodes[edge["end"]]
        if (
            left["curricular"]
            or right["curricular"]
            or left["id"] == right["id"]
            or left["type"] not in TASKS
            or right["type"] not in TASKS
        ):
            continue
        for book_id, refs in sourced_refs(edge["sources"], snapshot.books).items():
            book = snapshot.books[book_id]
            prompt = (
                f"Theo {book['title']} ({book.get('year', 'không rõ năm')}), "
                f"trình bày mối liên hệ được nguồn nêu giữa “{left['title']}” "
                f"và “{right['title']}”, trong phạm vi trang được dẫn. "
                "Nêu điều kiện áp dụng hoặc giới hạn nếu có; "
                "không suy ra quan hệ nhân quả khi nguồn không nêu."
            )
            basis = [
                {
                    "relation_type": edge["type"],
                    "condition": edge.get("condition", ""),
                    "sources": refs,
                }
            ]
            add_question(bank, [left, right], book, refs, prompt, basis, "source_relation")
    return bank


def add_question(bank, nodes, book, refs, prompt, basis, task):
    if len(prompt) > 4000:
        return
    data = {
        "generator_version": VERSION,
        "node_ids": [n["id"] for n in nodes],
        "node_revisions": {n["id"]: n["revision"] for n in nodes},
        "source_sha256": book["sha256"],
        "sources": refs,
        "basis": basis,
        "title": prompt,
        "task": task,
    }
    revision = fingerprint(data)
    identifier = "KGQ:" + revision
    bank[identifier] = {
        "id": identifier,
        "title": prompt,
        "revision": revision,
        "origin": "kg_template",
        "task": task,
        "book_ids": [book["id"]],
        "chapters": chapters_for(refs, book),
        "sources": refs,
        "node_ids": data["node_ids"],
        "provenance": {
            "generator_version": VERSION,
            "node_revisions": data["node_revisions"],
            "source_sha256": book["sha256"],
            "source_year": book.get("year"),
        },
        "study_basis": basis,
        "review_status": "needs_review",
        "expert_verified": False,
    }


def question_view(question, *, show_basis=False):
    # Catalog and draft responses contain citations/locators, not answer-bearing excerpts.
    result = {k: v for k, v in question.items() if k != "study_basis"}
    if question.get("origin") == "kg_template" and not show_basis:
        result["sources"] = [{**r, "excerpt": ""} for r in question["sources"]]
    if show_basis and "study_basis" in question:
        result["study_basis"] = question["study_basis"]
    return result


def search_questions(bank, *, q="", book="", chapter=None, origin="all", node_ids=None):
    text = folded(q)
    rows = [
        row
        for row in bank.values()
        if (not book or book in row["book_ids"])
        and (
            chapter is None
            or any(
                c["number"] == chapter and (not book or c["source_id"] == book)
                for c in row["chapters"]
            )
        )
        and (origin == "all" or (row.get("origin") == "book") == (origin == "book"))
        and (not text or text in folded(row["title"]))
        and (node_ids is None or bool(set(row.get("node_ids", [])) & node_ids))
    ]
    return sorted(rows, key=lambda r: (r.get("origin") != "book", r["title"], r["id"]))
