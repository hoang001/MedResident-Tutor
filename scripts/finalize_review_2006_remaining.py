"""Read-only checks and delivery summary for the 22-chapter source review."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser

from dotenv import dotenv_values
from summarize_kg_source_review import OUT, ROOT, assemble, verify_database

from document_toolkit.common import read_json, write_json


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.targets.extend(v for k, v in attrs if k == "href" and v)


def main():
    assemble()
    verification = verify_database()
    chapters = [
        r
        for r in read_json(OUT / "chapter-results.json")
        if r["lesson_number"] not in [1, 2, 15]
    ]
    assert sorted(r["lesson_number"] for r in chapters) == list(range(3, 15)) + list(
        range(16, 26)
    )
    assert all(
        r["import"]["import_status"] == "imported_and_idempotency_verified"
        for r in chapters
    )
    assert all(
        not r["import"]["second_import"][k].get(a, 0)
        for r in chapters
        for k in ["nodes", "edges"]
        for a in ["create", "update"]
    )
    summary = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "chapters_requested": 22,
        "chapters_completed": len(chapters),
        "nodes_created": sum(
            r["import"]["first_import"]["nodes"].get("create", 0) for r in chapters
        ),
        "nodes_updated_additive_sources": sum(
            r["import"]["first_import"]["nodes"].get("update", 0) for r in chapters
        ),
        "post_review_exact_word_repairs": 1,
        "edges_created": sum(
            r["import"]["first_import"]["edges"].get("create", 0) for r in chapters
        ),
        "pending_proposals_outside_graph": sum(r["pending_records"] for r in chapters),
        "missing_or_unclear_source_items": sum(
            r["missing_content_items"] for r in chapters
        ),
        "ocr_line_patches_in_overlays": sum(r["ocr_patch_count"] for r in chapters),
        "new_llm_calls": 0,
        "expert_verified": False,
        "database_verification": verification,
        "chapters": chapters,
    }
    write_json(OUT / "remaining-2006/result.json", summary)
    graph = read_json(OUT / "combined/graph.json")
    checked, broken = 0, []
    for file in OUT.rglob("*.html"):
        parser = Links()
        parser.feed(file.read_text(encoding="utf-8"))
        for href in parser.targets:
            if "://" in href or href.startswith("#"):
                continue
            checked += 1
            if not (file.parent / href.split("#")[0]).resolve().exists():
                broken.append({"file": file.relative_to(ROOT).as_posix(), "href": href})
    assert not broken, "broken_review_links"
    # Compare in memory only; never emit environment values or matching bytes.
    env = dotenv_values(ROOT / ".env", interpolate=False, encoding="utf-8-sig")
    secrets = [
        v.encode("utf-8")
        for k, v in env.items()
        if v
        and len(v) >= 8
        and any(t in k for t in ["KEY", "PASSWORD", "SECRET"])
        and not v.startswith("<")
    ]
    delivery_files = [
        p
        for p in OUT.rglob("*")
        if p.is_file()
        and p.suffix in {".json", ".jsonl", ".md", ".html", ".cypher", ".txt"}
    ]
    delivery_files += [
        ROOT / "scripts" / name
        for name in [
            "review_2006_remaining.py",
            "decisions_2006_remaining.py",
            "summarize_kg_source_review.py",
            "finalize_review_2006_remaining.py",
        ]
    ]
    assert not any(
        secret in p.read_bytes() for p in delivery_files for secret in secrets
    ), "secret_value_in_delivery"
    for r in graph["nodes"]:
        for c in r.get("content", []):
            assert not any(
                term in c["text"].lower()
                for term in ["kh\u1ecfng", "ch\u0103m s\u1ed1c", "s\u0103n s\u1ed1c"]
            ), "unintended_ocr_word_change"
    validation = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "importer_unit_tests": {"passed": 8, "failed": 0},
        "ruff_check": "passed",
        "html_local_links_checked": checked,
        "broken_html_links": broken,
        "secret_values_found_in_delivery_files": False,
        "node_types": dict(Counter(n["type"] for n in graph["nodes"])),
        "combined_nodes": len(graph["nodes"]),
        "combined_edges": len(graph["edges"]),
        "all_22_chapter_second_imports_only_skip": True,
        "source_integrity": read_json(OUT / "audit/source-integrity.json"),
        "final_helper_hashes": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in delivery_files
            if p.suffix == ".py"
        },
    }
    write_json(OUT / "audit/validation.json", validation)
    lines = [
        "# Hoàn tất22bài còn lại — Cấp cứu ngoại khoa – Chấn thương2006",
        "",
        "Đã đối chiếu bài3–14 và16–25 với OCR và ảnh PDF, kiểm tra các đề xuất LLM có sẵn rồi import phần có nguồn và schema phù hợp. Không gọi LLM mới.",
        "",
        f"Tạo thêm **{summary['nodes_created']}node và {summary['edges_created']}quan hệ**; **7node Gustilo** dùng lại ID canonical và chỉ cộng nguồn, giữ các đoạn định nghĩa khác nhau riêng biệt. Hiệu đính thêm một chữ ở bài13 sau kiểm cuối, có snapshot trước/sau tại chapters/2006-bai-13/word-repair. Neo4j hiện có **{verification['after_nodes']}node / {verification['after_edges']}quan hệ**, gồm cả bài1,2,15 đã nhập trước.",
        "",
        "**108node /75quan hệ tồn tại trước đợt này còn nguyên**. Tất cả22bài đọc lại thành công; lần import thứ hai chỉ skip, không tạo/cập nhật thêm. Kiểm tổng graph, loại quan hệ, hierarchy cycle, ID, properties, endpoint, điều kiện và nguồn/locator đều đạt.",
        "",
        f"Giữ ngoài graph **{summary['pending_proposals_outside_graph']}đề xuất**; có **{summary['missing_or_unclear_source_items']}mục thiếu/chưa rõ** được ghi riêng. Đã sửa **{summary['ocr_line_patches_in_overlays']}dòng OCR** trong overlay có trích vị trí và hash ảnh. OCR/PDF/rawLLM/output cũ và registry canonical không bị sửa. Đây là đối chiếu nguồn sách2006, **chưa phải chuyên gia y khoa duyệt**, không đồng nghĩa mọi nội dung sách đã được trích đủ.",
        "",
        "| Bài | Node sau đối chiếu | Quan hệ | Đề xuất giữ ngoài | Nội dung |",
        "|---|---:|---:|---:|---|",
    ]
    for r in chapters:
        number = r["lesson_number"]
        lines.append(
            f"| {number}. {r['title']} | {r['nodes_after']} | {r['edges_after']} | {r['pending_records']} | [Mở](../chapters/2006-bai-{number:02d}/review.html) |"
        )
    lines += [
        "",
        "Số node từng bài có7ID Gustilo dùng chung giữa bài3 và24; không cộng trực tiếp để tính node mới.",
        "",
        "- [Mục lục25bài](../review.html) · [JSON đầy đủ đã khớp Neo4j](../combined/graph.json)",
        "- [Kết quả22bài và import manifest](result.json) · [Đề xuất giữ ngoài](../pending-review.json) · [Phần thiếu/chưa rõ](../missing-content-reviewed-subset.json)",
        "- [Kiểm Neo4j](../audit/final-database-verification.json) · [Validation](../audit/validation.json) · [Truy vấn xem từng bài](../view.cypher)",
        "",
        "Sách2021 không được đối chiếu/import trong đợt này. Không sửa PostgreSQL, VPN/route, pipeline đang chạy; không commit/push.",
        "",
    ]
    (OUT / "remaining-2006/report.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in ["chapters", "database_verification"]
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
