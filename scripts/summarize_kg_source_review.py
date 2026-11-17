"""Assemble reviewed subsets and honest remaining queues; optional read-only DB check."""

import argparse
import hashlib
import html
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import (
    build_plan,
    merge_content,
    merge_unique,
    validate_locators,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/knowledge-extraction/v2/source-review-20261102"
PRIOR = (
    ROOT / "data/knowledge-extraction/v2/chapter-shoulder-2006-source-review-20261102"
)


def jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in values),
        encoding="utf-8",
    )


def verify_database():
    from dotenv import dotenv_values
    from neo4j import READ_ACCESS, GraphDatabase

    from knowledge_pipeline.neo4j_export import read_graph

    values = dotenv_values(ROOT / ".env", interpolate=False, encoding="utf-8-sig")
    target = read_json(OUT / "audit/neo4j-target.json")
    if (values["NEO4J_URI"], values["NEO4J_DATABASE"]) != (
        target["uri"],
        target["database"],
    ):
        raise ValueError("configured_database_changed_since_review_started")
    with (
        GraphDatabase.driver(
            values["NEO4J_URI"],
            auth=(values["NEO4J_USERNAME"], values["NEO4J_PASSWORD"]),
            connection_timeout=5,
            connection_acquisition_timeout=10,
            max_transaction_retry_time=0,
        ) as driver,
        driver.session(
            database=values["NEO4J_DATABASE"], default_access_mode=READ_ACCESS
        ) as session,
        session.begin_transaction(timeout=60) as tx,
    ):
        after = read_graph(tx, None)
    task_baseline = OUT / "chapters/2006-bai-03/import-001/before-all.json"
    before = read_json(
        task_baseline if task_baseline.exists() else OUT / "audit/neo4j-before-all.json"
    )
    for key in ["nodes", "relationships"]:
        actual = {r["element_id"]: r for r in after[key]}
        if not all(actual.get(r["element_id"]) == r for r in before[key]):
            raise ValueError("previously_existing_graph_record_changed")
        identities = [
            r["properties"].get("id") for r in after[key] if r["properties"].get("id")
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate_graph_record_id")
    expected = read_json(OUT / "combined/graph.json")
    if {r["id"] for r in expected["nodes"]} != {
        r["properties"].get("id") for r in after["nodes"]
    }:
        raise ValueError("unexpected_database_node_scope")
    if {r["id"] for r in expected["edges"]} != {
        r["properties"].get("id") for r in after["relationships"]
    }:
        raise ValueError("unexpected_database_edge_scope")
    plan = build_plan(expected, after)
    if any(r["action"] != "skip" for kind in ["nodes", "edges"] for r in plan[kind]):
        raise ValueError("combined_payload_does_not_match_database_properties")
    write_json(OUT / "audit/neo4j-after-all.json", after)
    result = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "target": target,
        "before_nodes": len(before["nodes"]),
        "before_edges": len(before["relationships"]),
        "after_nodes": len(after["nodes"]),
        "after_edges": len(after["relationships"]),
        "all_preexisting_records_unchanged": True,
        "all_ids_unique": True,
        "graph_id_sets_match_reviewed_subset": True,
        "payload_properties_and_decoded_sources_verified_by_per_chapter_importer": True,
        "combined_payload_all_skip": True,
    }
    write_json(OUT / "audit/final-database-verification.json", result)
    return result


def assemble():
    inventory = read_json(OUT / "inventory.json")
    progress = read_json(OUT / "progress.json")
    folders = [(2006, 15, PRIOR, "previously_source_compared_and_imported")]
    for key, row in sorted(progress["chapters"].items()):
        if row["import_status"] == "imported_and_idempotency_verified":
            folders.append(
                (
                    row["book_year"],
                    row["lesson_number"],
                    ROOT / row["review_directory"],
                    "source_compared_this_pass",
                )
            )
    nodes, edges, pages, locs, included = {}, {}, {}, {}, []
    pending = []
    missing = []
    by_chapter = []
    for year, number, folder, role in sorted(folders):
        graph = read_json(folder / "graph.json")
        for key, target in [("nodes", nodes), ("edges", edges)]:
            for r in graph[key]:
                if r["id"] in target and target[r["id"]] != r:
                    # Explicitly confirmed registry IDs reused by lessons3/24.
                    allowed = {
                        "MC_bad6dfb5263c4aa18bde65efbebc79bc",
                        "MC_f903181961b044e68e303375f476538e",
                        "MC_7148dc6b07054c43b48206a422d47be2",
                        "MC_9312bc84a5944df68498a5feba6f6551",
                        "MC_1fcc25417c6c4b829f1a9f39ce1f7077",
                        "MC_d3d42831dee943f79b3083e44ee4850b",
                        "MC_72f1e6d2069148dc8a79dca0cd9cc8d1",
                    }
                    prior = target[r["id"]]
                    if (
                        key != "nodes"
                        or r["id"] not in allowed
                        or {
                            k: v
                            for k, v in prior.items()
                            if k not in ["content", "aliases"]
                        }
                        != {
                            k: v
                            for k, v in r.items()
                            if k not in ["content", "aliases"]
                        }
                    ):
                        raise ValueError("conflicting_same_id_requires_explicit_review")
                    target[r["id"]] = {
                        **prior,
                        "content": merge_content(prior["content"], r["content"]),
                        "aliases": merge_unique(prior["aliases"], r["aliases"]),
                    }
                else:
                    target[r["id"]] = r
        for r in map(
            json.loads,
            (folder / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines(),
        ):
            key = (r["source_id"], r["pdf_page"])
            if key in pages and pages[key] != r:
                raise ValueError("conflicting_corrected_page_revision")
            pages[key] = r
        for r in read_json(folder / "audit/locators.json"):
            if r["locator_id"] in locs and locs[r["locator_id"]] != r:
                raise ValueError("conflicting_locator_revision")
            locs[r["locator_id"]] = r
        included.append(
            {
                "book_year": year,
                "lesson_number": number,
                "role": role,
                "review_directory": folder.relative_to(ROOT).as_posix(),
                "node_ids": [n["id"] for n in graph["nodes"]],
                "edge_ids": [e["id"] for e in graph["edges"]],
            }
        )
        if role == "source_compared_this_pass":
            m = read_json(folder / "review-manifest.json")
            decisions = read_json(folder / "decisions.json")
            stats = {
                kind: dict(
                    Counter(d["decision"] for d in decisions if d["kind"] == kind)
                )
                for kind in ["node", "edge"]
            }
            by_chapter.append(
                {
                    **m,
                    "decision_counts_by_kind": stats,
                    "import": progress["chapters"][folder.name],
                }
            )
            for filename, target in [
                ("pending-review.json", pending),
                ("need-extraction.json", missing),
            ]:
                for r in read_json(folder / filename):
                    target.append({"book_year": year, "lesson_number": number, **r})
    combined = {
        "schema_version": "medical-kg-v2",
        "nodes": sorted(nodes.values(), key=lambda r: r["id"]),
        "edges": sorted(edges.values(), key=lambda r: r["id"]),
    }
    dry_run_loader(combined)
    write_json(OUT / "combined/graph.json", combined)
    jsonl(OUT / "combined/reviewed-nodes.jsonl", combined["nodes"])
    jsonl(OUT / "combined/reviewed-edges.jsonl", combined["edges"])
    jsonl(OUT / "combined/audit/pages.jsonl", pages.values())
    write_json(OUT / "combined/audit/locators.json", list(locs.values()))
    checked = validate_locators(combined, OUT / "combined")
    write_json(
        OUT / "combined/manifest.json",
        {
            "included_chapters": included,
            "graph_fingerprint": fingerprint(combined),
            "nodes": len(nodes),
            "edges": len(edges),
            "locators_checked": checked,
            "all_books_complete": False,
            "book_2006_all_25_chapters_source_compared_and_imported": len(included)
            == 25,
            "cross_book_merge_confirmed": False,
            "expert_verified": False,
            "note": "Only source-compared/imported subsets, including the preserved shoulder chapter. Unreviewed book extraction is excluded.",
        },
    )
    write_json(OUT / "pending-review.json", pending)
    write_json(OUT / "missing-content-reviewed-subset.json", missing)
    remaining = [
        r for r in inventory["chapters"] if r["review_status"] == "not_reviewed"
    ]
    write_json(OUT / "remaining-review.json", remaining)
    # Preserve detailed review/rejected proposals without declaring them medical
    # errors or scheduling another LLM call before source comparison.
    held_queue = []
    for row in remaining:
        for parent in row["selected_sources"]:
            for filename in ["review_items.json", "rejected.json"]:
                path = ROOT / parent / "audit" / filename
                if not path.exists():
                    continue
                for index, r in enumerate(read_json(path)):
                    candidate = r.get("candidate", r.get("original", {}))
                    held_queue.append(
                        {
                            "book_year": row["book_year"],
                            "lesson_number": row["lesson_number"],
                            "pdf_pages": row["pdf_pages"],
                            "audit_file": path.relative_to(ROOT).as_posix(),
                            "record_index": index,
                            "window_id": r.get("window_id"),
                            "local_id": r.get("local_id"),
                            "reason": r.get("reason"),
                            "block_ids": [
                                s["block_id"]
                                for s in candidate.get("identity_sources", [])
                                if isinstance(s, dict) and "block_id" in s
                            ]
                            if isinstance(candidate, dict)
                            and isinstance(candidate.get("identity_sources", []), list)
                            else [],
                            "status": "awaiting_source_review_not_automatically_an_error_or_reextract_request",
                        }
                    )
    jsonl(OUT / "pending-extraction-audit.jsonl", held_queue)
    protected = read_json(OUT / "audit/protected-hashes.json")
    changed = [
        name
        for name, value in protected.items()
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value
    ]
    if changed:
        raise ValueError("protected_source_changed:" + str(changed))
    write_json(
        OUT / "audit/source-integrity.json",
        {
            "checked_files": len(protected),
            "changed_files": [],
            "active_2021_batch_and_draft_registry_excluded_from_static_hash_check": True,
        },
    )
    write_json(OUT / "chapter-results.json", by_chapter)
    # Parameter examples are literal IDs from the graph, never generated Cypher.
    params = {
        f"ids_{y}_{n:02d}": r["node_ids"]
        for r in included
        for y, n in [(r["book_year"], r["lesson_number"])]
    }
    params["reviewed_ids"] = list(nodes)
    write_json(OUT / "browser-params.json", params)
    queries = ["// Neo4j Browser: paste the relevant :param command before its query."]
    for name, identifiers in params.items():
        if name == "reviewed_ids":
            continue
        queries += [
            "",
            ":param ids => " + json.dumps(identifiers) + ";",
            "MATCH (n) WHERE n.id IN $ids OPTIONAL MATCH (n)-[r]->(m) WHERE m.id IN $ids RETURN n,r,m;",
        ]
    queries += [
        "",
        "// Skill / SampleQuestion within all reviewed chapters",
        ":param reviewed_ids => " + json.dumps(params["reviewed_ids"]) + ";",
        "MATCH (s:Skill) WHERE s.id IN $reviewed_ids RETURN s;",
        "MATCH (q:SampleQuestion) WHERE q.id IN $reviewed_ids RETURN q;",
        "// No concept carrying confirmed content from both books in this reviewed subset.",
        "// Inspect provenance without assuming a cross-book merge:",
        "MATCH (n:MedicalConcept) WHERE n.id IN $reviewed_ids RETURN n.id,n.name,n.content;",
    ]
    (OUT / "view.cypher").write_text("\n".join(queries) + "\n", encoding="utf-8")
    lines = [
        "# Đối chiếu nguồn và import Neo4j — đợt 02/11/2026",
        "",
        "**Hoàn tất đối chiếu và import kết quả LLM của25/25bài sách Cấp cứu ngoại khoa – Chấn thương2006. Sách2021 chưa thuộc đợt đối chiếu này.**",
        "",
        "Đợt tiếp tục xử lý22bài:3–14 và16–25; bài1,2,15 được giữ từ các đợt trước. Mỗi bài đã đọc dossier toàn bộ node/cạnh/đề xuất giữ ngoài và xem trực tiếp trang PDF tương ứng. Đây là kiểm tra nguồn bằng Codex, chưa phải chuyên gia y khoa duyệt; không đồng nghĩa mọi câu trong sách đã thành node.",
        "",
        "| Sách / bài | PDF | Node trước → sau | Cạnh trước → sau | Neo4j mới | Chạy lại |",
        "|---|---|---|---|---|---|",
    ]
    new_counts = {
        kind: sum(
            r["import"]["first_import"][kind].get("create", 0)
            for r in by_chapter
            if r["lesson_number"] not in [1, 2, 15]
        )
        for kind in ["nodes", "edges"]
    }
    update_counts = {
        kind: sum(
            r["import"]["first_import"][kind].get("update", 0) for r in by_chapter
        )
        for kind in ["nodes", "edges"]
    }
    for row in by_chapter:
        imp = row["import"]
        f = imp["first_import"]
        s = imp["second_import"]
        lines.append(
            f"| 2006 / {row['lesson_number']}. {row['title']} | {min(row['pdf_actually_viewed'])}–{max(row['pdf_actually_viewed'])} | {row['nodes_before']} → {row['nodes_after']} | {row['edges_before']} → {row['edges_after']} | {f['nodes'].get('create', 0)} node, {f['edges'].get('create', 0)} cạnh | {s['nodes'].get('skip', 0)} / {s['edges'].get('skip', 0)} bỏ qua |"
        )
    lines += [
        "| 2006 / 15. Trật khớp vai | 89–92 | 38 giữ nguyên | 34 giữ nguyên | Đã nhập từ trước | Bảo toàn |",
        "",
        f"Bộ dữ liệu đã đối chiếu gồm {len(nodes)} node / {len(edges)} cạnh, trong đó {new_counts['nodes']} node / {new_counts['edges']} cạnh mới ở đợt22bài này. Cập nhật cộng nguồn {update_counts['nodes']} node / {update_counts['edges']} cạnh, không xóa/reset graph. Importer đọc lại properties, labels, endpoints, conditions, decoded sources và kiểm dữ liệu ngoài phạm vi sau mỗi lần ghi.",
        "",
        f"Có {len(pending)} đề xuất giữ ngoài graph, cộng dồn các overlay bài1–14 và16–25. Có {len(missing)} mục thiếu/chưa rõ, xem missing-content-reviewed-subset.json. Các quyết định theo node/cạnh và trước/sau nằm ở chapter-results.json và chapters/*/decisions.json.",
        "",
        "Các sửa đáng chú ý: cành tươi/cẳng tay; gối/gót; đùi/dài; sụn/sự; mủ/mỡ; rễ/rẽ. Khôi phục ngoại lệ vết cắn, vị trí đầu mặt/bàn tay, điều kiện phẫu thuật và phủ định. Không biến trật khuỷu thành subtype gãy xương. Graft che nơi cho vạt không được nối nhầm thành graft che gót.",
        "",
        "Chưa xác nhận merge xuyên hai sách. Registry/binding được kiểm nhưng không ghi; không merge theo tên. Các loại gãy trẻ em có phạm vi riêng so với biến chứng ở chương vai. Caption thực của Hình2.1/2.2 đã xem và giữ trong audit; không ép “lồi cầu” và “trên lồi cầu” đồng nghĩa.",
        "",
        f"Bộ đã nhập có {sum(n['type'] == 'Skill' for n in nodes.values())} Skill và {sum(n['type'] == 'SampleQuestion' for n in nodes.values())} SampleQuestion. Chỉ phục hồi Skill có cơ sở thao tác/yêu cầu người học rõ trong nguồn, không biến bài tập của bệnh nhân thành Skill và không tự tạo câu hỏi.",
        "",
        "## Phần còn lại",
        "",
        f"{len(remaining)} bài chưa đối chiếu nguồn, đều thuộc2021. Sách2021 lấy snapshot từ shard đã hoàn tất, không đánh dấu extraction là đã duyệt. Thiếu đầu bài10,14,16,18 trong PDF2021 được ghi riêng, không để LLM tự điền.",
        "",
        "Các con số cửa sổ/phạm vi từng bài ở [inventory.md](inventory.md). Đã chọn 23 bài từ batch2006 mới (250 cửa sổ), cộng bài15/bài16 từ lineage trước (9 cửa sổ mỗi bài), không cộng các run thử hoặc recovery chồng nhau. Run sửa checkpoint2006 đã được phản ánh trong final shards; bản sao before không phải kết quả độc lập.",
        "",
        "## Mở dữ liệu và kiểm tra",
        "",
        "- [Mục lục review25bài](review.html): mở từng bài để xem đầy đủ node, nội dung, quan hệ, nguồn và các quyết định.",
        "- [Review vai đã có](../chapter-shoulder-2006-source-review-20261102/review.html)",
        "- [Graph sau đối chiếu](combined/graph.json) · [Manifest bộ dữ liệu](combined/manifest.json)",
        "- [Tiến độ](progress.json) · [Bài còn lại](remaining-review.json) · [Cần quyết định](pending-review.json)",
        "- Import manifest/snapshot ở chapters/2006-bai-XX/import-001; lần kiểm lặp tương ứng import-002. Đợt22bài tạo thêm dữ liệu, chỉ7node Gustilo có cập nhật cộng nguồn, không đổi định danh hay ghi đè nội dung cũ.",
        "- [Truy vấn Browser theo ID](view.cypher) · [Thông số ID](browser-params.json)",
        "- [Kiểm graph trước/sau](audit/final-database-verification.json) · [Hash nguồn gốc](audit/source-integrity.json)",
        "- [Kiểm tra importer, lint, liên kết review và bảo mật đầu ra](audit/validation.json)",
        "",
        "## Tiếp tục từ checkpoint",
        "",
        "Chạy từ thư mục gốc repo bằng PowerShell:",
        "",
        "```powershell",
        "$env:PYTHONPATH=(Get-Location).Path",
        '& "$env:TEMP/medresident-draft-venv/Scripts/python.exe" scripts/review_kg_sources.py --resume --apply-ready',
        '& "$env:TEMP/medresident-draft-venv/Scripts/python.exe" scripts/summarize_kg_source_review.py --verify-db',
        "```",
        "",
        f"Lệnh trên làm mới inventory/báo cáo và chỉ import overlay đã được đối chiếu, có fingerprint phù hợp. Nó KHÔNG tự duyệt hoặc tự trích xuất {len(remaining)} bài còn lại. Bước đối chiếu tiếp theo bắt đầu từ remaining-review.json, tạo overlay mới sau khi đọc nguồn rồi mới chạy apply-ready.",
        "",
        "Không gọi LLM, không sửa pipeline đang chạy, nguồn OCR/PDF, raw/output cũ, PostgreSQL hay dữ liệu ứng dụng; không commit/push.",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cards = [
        '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Review nguồn KG</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 18px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left}.pending{background:#fff5da;padding:16px}small{color:#555}</style>',
        "<h1>Đối chiếu nguồn KG — tiến độ từng bài</h1>",
        '<div class="pending"><b>Đã đối chiếu/import25bài sách2006; sách2021 chưa đối chiếu.</b><p>Đợt tiếp tục đã xử lý22bài còn lại. '
        + str(len(pending))
        + " đề xuất giữ ngoài và "
        + str(len(missing))
        + ' mục thiếu/chưa rõ cần xem tiếp. <a href="pending-review.json">Đề xuất</a> · <a href="missing-content-reviewed-subset.json">Phần thiếu</a></p><p>Chưa phải chuyên gia y khoa duyệt. Không dùng kiến thức ngoài cập nhật sách.</p></div>',
        '<p><a href="report.md">Báo cáo</a> · <a href="combined/graph.json">JSON sau đối chiếu</a> · <a href="inventory.md">Inventory</a> · <a href="remaining-review.json">Bài còn lại</a> · <a href="view.cypher">Truy vấn Neo4j</a></p>',
    ]
    for year in [2006, 2021]:
        cards += [
            "<h2>Sách "
            + str(year)
            + "</h2><table><tr><th>Bài / trang PDF</th><th>Cửa sổ</th><th>Node/cạnh extraction</th><th>Trạng thái và review</th></tr>"
        ]
        for row in inventory["chapters"]:
            if row["book_year"] != year:
                continue
            pages_range = row["pdf_pages"]
            directory = row.get("review_directory")
            link = ""
            if directory:
                relative = (
                    Path(directory).relative_to(OUT.relative_to(ROOT)).as_posix()
                    if str(directory).startswith(OUT.relative_to(ROOT).as_posix() + "/")
                    else "../chapter-shoulder-2006-source-review-20261102"
                )
                link = ' <a href="' + relative + '/review.html">Mở nội dung</a>'
            cards += [
                f"<tr><td>{row['lesson_number']}. {html.escape(row['title'])}<br><small>{pages_range['start']}–{pages_range['end']}</small></td><td>{row['processed_windows']}/{row['expected_windows']}<br><small>partial {row['partial_windows']}, lỗi {row.get('failed_windows', 0)}</small></td><td>{row['nodes_before']} / {row['edges_before']}</td><td>{html.escape(row['review_status'])}{link}</td></tr>"
            ]
        cards += ["</table>"]
    (OUT / "review.html").write_text("\n".join(cards) + "</html>", encoding="utf-8")
    return {
        "reviewed_nodes": len(nodes),
        "reviewed_edges": len(edges),
        "newly_reviewed_chapters": len(by_chapter),
        "remaining_2006_chapters_this_request_completed": sum(
            r["lesson_number"] not in [1, 2, 15] for r in by_chapter
        ),
        "remaining_chapters": len(remaining),
        "pending_records_this_pass": len(pending),
        "protected_files_unchanged": len(protected),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-db",
        action="store_true",
        help="Read configured Neo4j and compare with the snapshot; no writes",
    )
    args = parser.parse_args()
    result = assemble()
    if args.verify_db:
        result["database_verification"] = verify_database()
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
