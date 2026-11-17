"""Build/apply an additive, source-located reading map for four Round 2 courses.

Preview: python -m scripts.map_round2_books
Apply:   python -m scripts.map_round2_books --apply
No LLM, OCR, clinical edits, schema changes, or elective-course writes.
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "data/curriculum/round2_book_mapping.json"
CATALOG = ROOT / "data/library/catalog.json"
OUTPUT = ROOT / "data/curriculum/round2-mapping"
MANAGER = "medresident-round2-books-v1"
PROGRAM = "HMU_RESIDENCY_SURGERY_ORTHOPEDICS_2025"
CODES = {"B21CN7", "B21CN8", "B21CN9", "B21CN10"}
SOURCES = {2006: "SRC_ORTHO_EMERGENCY_001", 2021: "SRC_ORTHO_TEXTBOOK_001"}
LABELS = {"StudyBook", "StudyChapter", "CourseStudyPlan"}
RELATIONS = {"HAS_STUDY_PLAN", "HAS_READING", "HAS_CHAPTER", "HAS_EXTRACTED_NODE"}
CLINICAL_LABELS = {"MedicalConcept", "Skill", "SampleQuestion"}
ROLES = {"primary_reading", "shared_reference", "supplementary_reading", "related_reading"}
ROLE_NAMES = {
    "primary_reading": "Bài đọc chính đề xuất",
    "shared_reference": "Tài liệu dùng chung, ôn theo nhu cầu",
    "supplementary_reading": "Đọc bổ trợ",
    "related_reading": "Chủ đề liên quan, chờ xác nhận",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def unpack(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, list):
        raise ValueError("source_list_required")
    return result


def citations(props):
    refs = list(unpack(props.get("sources", [])))
    for block in unpack(props.get("content", [])):
        refs += block.get("sources", [])
    return refs


def edge(kind, start, end, **props):
    if kind not in RELATIONS:
        raise ValueError("unsupported_mapping_relation")
    return {
        "type": kind, "from_id": start, "to_id": end,
        "properties": {
            "id": MANAGER + ":EDGE:" + digest([kind, start, end])[:32],
            "managed_by": MANAGER, **props,
        },
    }


def build_graph(spec, catalog, snapshot):
    if (spec.get("program_id") != PROGRAM
            or spec.get("status") != "provisional_awaiting_teacher_confirmation"
            or any(spec.get(k) is not False for k in (
                "official_syllabus_confirmed", "clinical_currency_verified", "practice_credit_awarded"))):
        raise ValueError("unsupported_mapping_scope_or_claim")
    if {c["course_code"] for c in spec["courses"]} != CODES or len(spec["courses"]) != 4:
        raise ValueError("exactly_four_round2_courses_required")
    books = {b["year"]: b for b in catalog["books"] if b["id"] in SOURCES.values()}
    if {y: b["id"] for y, b in books.items()} != SOURCES:
        raise ValueError("two_verified_book_identities_required")
    index = defaultdict(list)
    for n in snapshot["nodes"]:
        if n["properties"].get("id"):
            index[n["properties"]["id"]].append(n)
    clinical = [n for n in snapshot["nodes"] if set(n["labels"]) & CLINICAL_LABELS]
    nodes, edges, chapters, courses = {}, [], {}, []
    base = {"managed_by": MANAGER, "mapping_status": spec["status"],
            "official_syllabus_confirmed": False, "expert_verified": False}

    def add_node(kind, identifier, **props):
        if kind not in LABELS:
            raise ValueError("unsupported_mapping_label")
        row = {"labels": [kind], "properties": {**base, "id": identifier, **props}}
        if identifier in nodes and nodes[identifier] != row:
            raise ValueError("conflicting_mapping_node")
        nodes[identifier] = row

    for year, book in books.items():
        book_id = MANAGER + ":BOOK:" + book["id"]
        add_node("StudyBook", book_id, source_id=book["id"], name=book["title"],
                 publication_year=year, source_sha256=book["sha256"],
                 pdf_page_count=book["pages"], clinical_currency_verified=False)
    for course in spec["courses"]:
        code = course["course_code"]
        course_id = "CURRICULUM:" + PROGRAM + ":COURSE:" + code
        matches = index[course_id]
        if len(matches) != 1 or "Course" not in matches[0]["labels"]:
            raise ValueError("existing_course_not_unique:" + code)
        props = matches[0]["properties"]
        if any(props.get(k) != v for k, v in {
            "curriculum_id": PROGRAM, "course_code": code, "round": 2,
            "theory_credits": 1, "practice_credits": 5, "total_credits": 6,
        }.items()):
            raise ValueError("existing_course_metadata_mismatch:" + code)
        plan_id = MANAGER + ":PLAN:" + code
        add_node("CourseStudyPlan", plan_id, name="Bản đồ bài đọc – " + props["name"],
                 course_code=code, curriculum_id=PROGRAM, coverage_status=course["coverage"],
                 coverage_note=course["coverage_note"], pending_confirmation=course["pending"],
                 purpose="Tự học lý thuyết và chuẩn bị trước thực hành",
                 order_status="proposed_not_official", practice_credit_awarded=False,
                 clinical_currency_verified=False, definition_sha256=digest(course))
        edges.append(edge("HAS_STUDY_PLAN", course_id, plan_id))
        seen, order = set(), 0
        for reading in course["readings"]:
            year = reading["source_year"]
            if year not in books or reading["role"] not in ROLES:
                raise ValueError("invalid_reading_book_or_role")
            book = books[year]
            for number in reading["chapters"]:
                key = (year, number)
                if key in seen:
                    raise ValueError("duplicate_course_chapter")
                seen.add(key)
                options = [c for c in book["chapters"] if c["number"] == number]
                if len(options) != 1:
                    raise ValueError("chapter_not_unique_in_catalog")
                chapter = options[0]
                if not 1 <= chapter["start"] <= chapter["end"] <= book["pages"]:
                    raise ValueError("invalid_chapter_page_range")
                chapter_id = MANAGER + ":CHAPTER:" + book["id"] + ":" + str(number)
                chapters[key] = chapter_id
                add_node("StudyChapter", chapter_id,
                         name=f"Bài {number}. {chapter['title']} ({year})",
                         chapter_title=chapter["title"], chapter_number=number,
                         source_id=book["id"], source_sha256=book["sha256"],
                         pdf_page_start=chapter["start"], pdf_page_end=chapter["end"],
                         page_numbering="pdf_1_based", source_opening_missing=bool(chapter.get("opening_missing")),
                         membership_scope="cited_content_only_not_entire_concept",
                         evidence_method="catalog_chapter_bounds_and_existing_source_citations")
                order += 1
                edges.append(edge("HAS_READING", plan_id, chapter_id,
                                  role=reading["role"], stage=reading["stage"], display_order=order,
                                  purpose=reading["purpose"], required_by_official_syllabus=False,
                                  mapping_status=spec["status"]))
        courses.append({"course_code": code, "name": props["name"], "plan_id": plan_id,
                        "readings": order, "coverage_status": course["coverage"],
                        "coverage_note": course["coverage_note"], "pending": course["pending"]})
    selected = defaultdict(list)
    for (year, number), chapter_id in sorted(chapters.items()):
        p = nodes[chapter_id]["properties"]
        edges.append(edge("HAS_CHAPTER", MANAGER + ":BOOK:" + p["source_id"], chapter_id))
        selected[p["source_id"]].append(p)
    for n in clinical:
        p = n["properties"]
        if not isinstance(p.get("id"), str) or len(index[p["id"]]) != 1:
            raise ValueError("clinical_node_id_missing_or_ambiguous")
        matches = defaultdict(lambda: {"pdf_pages": set(), "locator_ids": set()})
        for ref in citations(p):
            for chapter in selected.get(ref.get("source_id"), []):
                pages = {page for page in ref.get("pdf_pages", [])
                         if type(page) is int and chapter["pdf_page_start"] <= page <= chapter["pdf_page_end"]}
                if pages:
                    match = matches[chapter["id"]]
                    match["pdf_pages"].update(pages)
                    if ref.get("locator_id"):
                        match["locator_ids"].add(ref["locator_id"])
        for chapter_id, match in sorted(matches.items()):
            edges.append(edge("HAS_EXTRACTED_NODE", chapter_id, p["id"],
                              source_id=nodes[chapter_id]["properties"]["source_id"],
                              pdf_pages=sorted(match["pdf_pages"]), locator_ids=sorted(match["locator_ids"]),
                              membership_scope="cited_content_only_not_entire_concept"))
    if len({e["properties"]["id"] for e in edges}) != len(edges):
        raise ValueError("duplicate_mapping_edge")
    graph = {"format": "medresident-round2-reading-graph-v1", "manager": MANAGER,
             "definition_sha256": digest(spec), "nodes": list(nodes.values()), "edges": edges}
    for course in courses:
        chapter_ids = {e["to_id"] for e in edges if e["type"] == "HAS_READING" and e["from_id"] == course["plan_id"]}
        course["linked_existing_nodes"] = len({e["to_id"] for e in edges if e["type"] == "HAS_EXTRACTED_NODE" and e["from_id"] in chapter_ids})
    graph["summary"] = {
        "courses": courses, "new_nodes": len(nodes), "new_relationships": len(edges),
        "labels": dict(Counter(n["labels"][0] for n in nodes.values())),
        "relationship_types": dict(Counter(e["type"] for e in edges)),
        "distinct_existing_clinical_nodes": len({e["to_id"] for e in edges if e["type"] == "HAS_EXTRACTED_NODE"}),
        "chapters_with_source_opening_missing": [n["properties"]["name"] for n in nodes.values() if n["properties"].get("source_opening_missing")],
    }
    return graph


def read_snapshot(tx):
    return {
        "nodes": [dict(r) for r in tx.run(
            "MATCH (n) RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS properties ORDER BY element_id")],
        "relationships": [dict(r) for r in tx.run(
            "MATCH (a)-[r]->(b) RETURN elementId(r) AS element_id, type(r) AS type, "
            "elementId(a) AS start_node, elementId(b) AS end_node, properties(r) AS properties ORDER BY element_id")],
    }


def plan_changes(graph, snapshot):
    nodes, rels = defaultdict(list), defaultdict(list)
    for n in snapshot["nodes"]:
        nodes[n["properties"].get("id")].append(n)
    for r in snapshot["relationships"]:
        rels[r["properties"].get("id")].append(r)
    by_element = {n["element_id"]: n["properties"].get("id") for n in snapshot["nodes"]}
    new_nodes, new_edges = [], []
    known = set(nodes) | {n["properties"]["id"] for n in graph["nodes"]}
    for n in graph["nodes"]:
        matches = nodes.get(n["properties"]["id"], [])
        if matches and (len(matches) != 1 or set(matches[0]["labels"]) != set(n["labels"])
                        or matches[0]["properties"] != n["properties"]):
            fields = sorted(k for k in set(matches[0]["properties"]) | set(n["properties"])
                            if matches[0]["properties"].get(k) != n["properties"].get(k))
            raise ValueError("existing_mapping_node_conflict:" + n["properties"]["id"] + ":fields=" + ",".join(fields))
        if not matches:
            new_nodes.append(n)
    for e in graph["edges"]:
        if e["from_id"] not in known or e["to_id"] not in known:
            raise ValueError("missing_mapping_endpoint")
        matches = rels.get(e["properties"]["id"], [])
        if matches:
            if len(matches) != 1:
                raise ValueError("duplicate_existing_mapping_edge")
            old = matches[0]
            if (old["type"], by_element[old["start_node"]], by_element[old["end_node"]], old["properties"]) != (
                    e["type"], e["from_id"], e["to_id"], e["properties"]):
                raise ValueError("existing_mapping_edge_conflict")
        else:
            new_edges.append(e)
    return {"nodes": new_nodes, "edges": new_edges}


def verify_preserved(before, after):
    for key in ("nodes", "relationships"):
        actual = {row["element_id"]: row for row in after[key]}
        for original in before[key]:
            if actual.get(original["element_id"]) != original:
                raise ValueError("existing_graph_modified:" + key)


def apply_graph(tx, graph, before):
    if digest(read_snapshot(tx)) != digest(before):
        raise ValueError("graph_changed_since_backup")
    changes = plan_changes(graph, before)
    elements = {n["properties"].get("id"): n["element_id"] for n in before["nodes"]}
    for label in sorted(LABELS):
        rows = [n["properties"] for n in changes["nodes"] if n["labels"] == [label]]
        if rows:
            created = tx.run(
                f"UNWIND $rows AS row CREATE (n:{label}) SET n = row RETURN n.id AS id, elementId(n) AS element_id",
                rows=rows,
            )
            elements.update({r["id"]: r["element_id"] for r in created})
    for kind in sorted(RELATIONS):
        rows = [{**e, "start_element": elements[e["from_id"]], "end_element": elements[e["to_id"]]}
                for e in changes["edges"] if e["type"] == kind]
        if rows:
            tx.run(
                "UNWIND $rows AS row MATCH (a), (b) "
                "WHERE elementId(a)=row.start_element AND elementId(b)=row.end_element "
                f"CREATE (a)-[r:{kind}]->(b) SET r = row.properties", rows=rows,
            ).consume()
    after = read_snapshot(tx)
    verify_preserved(before, after)
    remaining = plan_changes(graph, after)
    if remaining["nodes"] or remaining["edges"]:
        raise ValueError("mapping_readback_incomplete")
    if (len(after["nodes"]) != len(before["nodes"]) + len(changes["nodes"])
            or len(after["relationships"]) != len(before["relationships"]) + len(changes["edges"])):
        raise ValueError("unexpected_graph_count_after_import")
    return after


def write_review(graph):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT / "graph.json", graph)
    write_json(OUTPUT / "summary.json", graph["summary"])
    index = {n["properties"]["id"]: n["properties"] for n in graph["nodes"]}
    lines = ["# Mapping đề xuất: hai sách → bốn học phần Round 2", "",
             "Đây là bản đồ bài đọc, chưa phải đề cương hoặc chuẩn đầu ra được trường phê duyệt. "
             "Mỗi môn vẫn giữ 1 tín chỉ lý thuyết + 5 tín chỉ thực hành. Không quy đổi đọc sách thành đạt thực hành.", "",
             "Sách 2021 được dùng làm nguồn đọc chính trong bản đề xuất này; sách 2006 để đối chiếu bổ trợ. "
             "Chưa xác nhận tính cập nhật lâm sàng của từng nội dung; hai nguồn không được gộp thành một phác đồ.", "",
             "Thứ tự đọc do dự án đề xuất, không phải lịch học chính thức. "
             "Một chương dùng chung cho nhiều môn, không sao chép node kiến thức. "
             "Liên kết tới node chỉ chứng minh có trích dẫn thuộc chương, không khẳng định toàn bộ node nằm trong chương.", ""]
    for course in graph["summary"]["courses"]:
        lines += ["## " + course["course_code"] + " – " + course["name"], "", course["coverage_note"], "",
                  "| Thứ tự đề xuất | Vai trò | Sách | Bài | Trang PDF | Nội dung |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for e in graph["edges"]:
            if e["type"] == "HAS_READING" and e["from_id"] == course["plan_id"]:
                p, c = e["properties"], index[e["to_id"]]
                year = 2021 if c["source_id"] == SOURCES[2021] else 2006
                title = c["chapter_title"] + (" **[Thiếu phần mở đầu nguồn]**" if c["source_opening_missing"] else "")
                lines.append(f"| {p['display_order']} | {ROLE_NAMES[p['role']]} | {year} | {c['chapter_number']} | {c['pdf_page_start']}–{c['pdf_page_end']} | {title} |")
        lines += ["", "Cần xác nhận/bổ sung:", "", *["- " + item for item in course["pending"]], ""]
    lines += ["## Nguồn và cách nối", "",
              "- Danh mục và trang chương: `data/library/catalog.json`.",
              "- Quy tắc phân chia: `data/curriculum/round2_book_mapping.json`.",
              "- Node cũ được nối bằng `source_id` + `pdf_pages` trong trích dẫn đã có; lưu lại `locator_ids` trên cạnh.",
              "- Không thêm chuẩn đầu ra, không đánh dấu chuyên gia duyệt, không sửa tám môn tự chọn.",
              "- Một số nguồn OCR có thiếu phần mở đầu; xem cảnh báo trên chương, không tự điền phần thiếu.", ""]
    (OUTPUT / "review.md").write_text("\n".join(lines), encoding="utf-8")
    (OUTPUT / "view.cypher").write_text(
        "// 4 môn và kế hoạch bài đọc\n"
        f"MATCH p=(c:Course)-[:HAS_STUDY_PLAN]->(s:CourseStudyPlan) WHERE s.managed_by='{MANAGER}' RETURN p;\n\n"
        "// Bài đọc của một môn: đổi course_code để xem môn khác\n"
        "MATCH p=(c:Course {course_code:'B21CN7'})-[:HAS_STUDY_PLAN]->(s:CourseStudyPlan)-[:HAS_READING]->(ch:StudyChapter)\n"
        f"WHERE s.managed_by='{MANAGER}' RETURN p;\n\n"
        "// Bảng thứ tự đọc\n"
        "MATCH (c:Course)-[:HAS_STUDY_PLAN]->(s:CourseStudyPlan)-[r:HAS_READING]->(ch:StudyChapter)\n"
        f"WHERE s.managed_by='{MANAGER}' RETURN c.course_code, r.display_order, r.role, ch.name, ch.pdf_page_start, ch.pdf_page_end ORDER BY c.course_code, r.display_order;\n\n"
        "// Chi tiết một bài, giới hạn 50 node để dễ xem\n"
        "MATCH p=(ch:StudyChapter {source_id:'SRC_ORTHO_TEXTBOOK_001', chapter_number:19})-[:HAS_EXTRACTED_NODE]->(n)\n"
        f"WHERE ch.managed_by='{MANAGER}' RETURN p LIMIT 50;\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from dotenv import dotenv_values
    from neo4j import GraphDatabase
    config = dotenv_values(ROOT / ".env", interpolate=False, encoding="utf-8-sig")
    keys = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
    if any(not config.get(k) or config[k].startswith("<") for k in keys):
        raise ValueError("fill_NEO4J_settings_in_root_env")
    with GraphDatabase.driver(
        config["NEO4J_URI"], auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
        connection_timeout=5, connection_acquisition_timeout=10, max_transaction_retry_time=0,
    ) as driver:
        with driver.session(database=config["NEO4J_DATABASE"]) as session:
            before = session.execute_read(read_snapshot)
            graph = build_graph(read_json(SPEC), read_json(CATALOG), before)
            changes = plan_changes(graph, before)
            write_review(graph)
            result = {"status": "preview", "mapping": graph["summary"],
                      "to_create": {k: len(v) for k, v in changes.items()}}
            if args.apply:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                backup = ROOT / "data/backups" / ("round2-mapping-" + stamp)
                write_json(backup / "before.json", before)
                with session.begin_transaction(timeout=120) as tx:
                    after = apply_graph(tx, graph, before)
                    tx.commit()
                write_json(backup / "after.json", after)
                # Verify again from a fresh read after commit.
                committed = session.execute_read(read_snapshot)
                verify_preserved(before, committed)
                pending = plan_changes(graph, committed)
                if pending["nodes"] or pending["edges"]:
                    raise ValueError("committed_mapping_incomplete")
                result.update(status="applied_and_verified", backup=backup.relative_to(ROOT).as_posix(),
                              before={"nodes": len(before["nodes"]), "relationships": len(before["relationships"])},
                              after={"nodes": len(after["nodes"]), "relationships": len(after["relationships"])},
                              existing_graph_unchanged=True, reapply_creates_zero=True)
            write_json(OUTPUT / "last-run.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Connection messages can include configuration; expose only safe error identifiers.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "error_code": getattr(exc, "code", None),
                          "reason": str(exc) if type(exc) is ValueError else None}))
        raise SystemExit(1) from None
