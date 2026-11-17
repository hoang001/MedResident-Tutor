"""Collect HMU public sources, validate exact citations and supplement Curriculum.

--collect prepares immutable snapshots, --prepare builds a reviewable graph,
--apply imports that graph transactionally. No LLM, clinical extraction or login.
"""

import argparse
import copy
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfReader

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.hmu_public import (
    course_listings,
    extract_plos,
    normalized_name,
    parse_html,
    program_sections,
    validate_hmu_url,
)
from knowledge_pipeline.neo4j_export import read_graph
from scripts.build_hmu_material_request import write_material_review
from scripts.import_curriculum import (
    LABELS,
    RELATIONS,
    ROOT,
    SOURCE,
    TREE_SOURCE,
    build_curriculum_tree,
    build_plan,
    build_skeleton,
    verify_graph,
    write_graph,
)

OUT = ROOT / "data/knowledge-extraction/hmu-public-20261104"
CACHE = OUT / "discovery"
PROGRAM_URL = "https://lms.hmu.edu.vn/course/index.php?categoryid=1944"
EXTRA_LABELS = {
    "CurriculumSource",
    "CurriculumObjective",
    "CurriculumOutcome",
    "CurriculumCareerPath",
    "CurriculumStudyPath",
    "CurriculumReference",
    "CurriculumCourseDescription",
}
EXTRA_RELATIONS = {
    "HAS_SOURCE",
    "HAS_OBJECTIVE",
    "HAS_PROGRAM_OUTCOME",
    "HAS_CAREER_PATH",
    "HAS_STUDY_PATH",
    "REFERENCES_FRAMEWORK",
    "SUPPORTED_BY",
    "HAS_DESCRIPTION",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_one(name, url):
    validate_hmu_url(url)
    meta_path = CACHE / (name + ".json")
    if meta_path.exists():
        meta = read_json(meta_path)
        if meta.get("url") != url:
            raise ValueError("snapshot_url_changed")
        if meta.get("file") and digest(CACHE / meta["file"]) != meta["sha256"]:
            raise ValueError("snapshot_hash_mismatch")
        if "fetched_at_utc" not in meta:
            meta["fetched_at_utc"] = datetime.fromtimestamp(
                (CACHE / meta["file"]).stat().st_mtime, UTC
            ).isoformat()
            write_json(meta_path, meta)
        return meta
    meta = {"name": name, "url": url, "fetched_at_utc": datetime.now(UTC).isoformat()}
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(35, connect=10),
            trust_env=False,
        ) as client:
            response = client.get(url)
        validate_hmu_url(str(response.url))
        if len(response.content) > 25_000_000:
            raise ValueError("hmu_snapshot_too_large")
        blocked = "/login/" in response.url.path
        meta.update(
            http_status=response.status_code,
            content_type=response.headers.get("content-type"),
            bytes=len(response.content),
            sha256=hashlib.sha256(response.content).hexdigest(),
            redirected_to_login=blocked,
        )
        if not blocked and response.status_code == 200:
            suffix = ".pdf" if response.content.startswith(b"%PDF-") else ".html"
            meta["file"] = name + suffix
            CACHE.mkdir(parents=True, exist_ok=True)
            (CACHE / meta["file"]).write_bytes(response.content)
    except (httpx.HTTPError, ValueError) as exc:
        meta["error_type"] = type(exc).__name__
        if isinstance(exc, ValueError):
            meta["reason"] = str(exc)
    write_json(meta_path, meta)
    return meta


def batch(jobs):
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        for future in as_completed(
            [executor.submit(collect_one, *job) for job in jobs]
        ):
            result = future.result()
            results.append(result)
    print(
        json.dumps(
            {
                "requests": len(results),
                "http_200": sum(r.get("http_status") == 200 for r in results),
                "login_required": sum(
                    bool(r.get("redirected_to_login")) for r in results
                ),
                "errors": [
                    {
                        "name": r["name"],
                        "error_type": r.get("error_type"),
                        "http_status": r.get("http_status"),
                    }
                    for r in results
                    if r.get("error_type") or r.get("http_status") != 200
                ],
            }
        ),
        flush=True,
    )


def load_html(name):
    meta = read_json(CACHE / (name + ".json"))
    validate_hmu_url(meta["url"])
    if (
        meta.get("http_status") != 200
        or not meta.get("file", "").endswith(".html")
        or meta.get("redirected_to_login")
    ):
        raise ValueError("hmu_public_html_unavailable")
    if digest(CACHE / meta["file"]) != meta["sha256"]:
        raise ValueError("snapshot_hash_mismatch")
    return (CACHE / meta["file"]).read_text(encoding="utf-8-sig"), meta


def match_courses(graph):
    catalog = []
    for year, name in [(1, "lms-year1"), (2, "lms-year2-all"), (3, "lms-year3-all")]:
        text, _ = load_html(name)
        catalog.extend(
            {**row, "year": year, "snapshot": name} for row in course_listings(text)
        )
    matches, missing = {}, []
    for node in graph["nodes"]:
        if node["type"] != "Course":
            continue
        p = node["properties"]
        candidates = (
            [r for r in catalog if r["course_code"] == p.get("course_code")]
            if p.get("course_code")
            else [
                r
                for r in catalog
                if normalized_name(r["course_name"]) == normalized_name(p["name"])
            ]
        )
        if len(candidates) == 1:
            matches[p["id"]] = candidates[0]
        elif not candidates:
            missing.append(
                {
                    "node_id": p["id"],
                    "name": p["name"],
                    "reason": "not_found_in_checked_hmu_year_listings",
                }
            )
        else:
            raise ValueError("ambiguous_hmu_course_match")
    return matches, missing


def collect():
    batch(
        [
            ("lms-program", PROGRAM_URL),
            ("lms-year1", "https://lms.hmu.edu.vn/course/index.php?categoryid=2419"),
            (
                "lms-year2-all",
                "https://lms.hmu.edu.vn/course/index.php?categoryid=2420&browse=courses&perpage=100",
            ),
            (
                "lms-year3-all",
                "https://lms.hmu.edu.vn/course/index.php?categoryid=2421&browse=courses&perpage=100",
            ),
        ]
    )
    text, _ = load_html("lms-program")
    box = next(
        n
        for n in parse_html(text).walk()
        if n.has_class("generalbox") and n.has_class("info")
    )
    attachments = [
        a.attrs["href"]
        for a in box.walk()
        if a.tag == "a" and a.attrs.get("href", "").endswith(".pdf")
    ]
    if len(attachments) != 4:
        raise ValueError("unexpected_hmu_program_attachment_count")
    batch([(f"lms-attachment-{i}", url) for i, url in enumerate(attachments, 1)])
    baseline = build_curriculum_tree(
        read_json(TREE_SOURCE), build_skeleton(read_json(SOURCE))
    )
    matches, missing = match_courses(baseline)
    batch(
        [
            (
                f"course-{r['lms_course_id']}-{kind}",
                f"https://lms.hmu.edu.vn/course/{'info' if kind == 'info' else 'view'}.php?id={r['lms_course_id']}",
            )
            for r in matches.values()
            for kind in ["info", "view"]
        ]
    )
    write_json(
        OUT / "course-listing-matches.json", {"matches": matches, "missing": missing}
    )


def make_evidence(name, locator, quote):
    meta = read_json(CACHE / (name + ".json"))
    validate_hmu_url(meta["url"])
    return {
        "source_url": meta["url"],
        "snapshot_path": (CACHE / meta["file"]).relative_to(ROOT).as_posix(),
        "source_sha256": meta["sha256"],
        "fetched_at_utc": meta["fetched_at_utc"],
        "locator": locator,
        "quote": quote,
    }


def validate_evidence(evidence):
    validate_hmu_url(evidence["source_url"])
    path = ROOT / evidence["snapshot_path"]
    if (
        not path.resolve().is_relative_to(CACHE.resolve())
        or digest(path) != evidence["source_sha256"]
    ):
        raise ValueError("invalid_hmu_source_snapshot")
    original = read_json(path.with_suffix(".json"))
    if (
        original["url"] != evidence["source_url"]
        or original["sha256"] != evidence["source_sha256"]
    ):
        raise ValueError("hmu_source_url_mismatch")
    loc = evidence["locator"]
    if loc["kind"] == "program_block":
        actual = program_sections(path.read_text(encoding="utf-8-sig"))[loc["index"]][
            "text"
        ]
    elif loc["kind"] == "course_title":
        actual = next(
            r["title"]
            for r in course_listings(path.read_text(encoding="utf-8-sig"))
            if r["lms_course_id"] == loc["lms_course_id"]
        )
    elif loc["kind"] == "pdf_text":
        text = PdfReader(path).pages[loc["page"] - 1].extract_text()
        actual = text[loc["start"] : loc["end"]]
    elif loc["kind"] == "course_summary":
        actual = next(
            r["summary"]
            for r in course_listings(path.read_text(encoding="utf-8-sig"))
            if r["lms_course_id"] == loc["lms_course_id"]
        )
    else:
        raise ValueError("unsupported_hmu_locator")
    if actual != evidence["quote"]:
        raise ValueError("hmu_quote_does_not_match_locator")


def pdf_evidence(name, page, text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return make_evidence(
        name,
        {"kind": "pdf_text", "page": page, "start": start, "end": end},
        text[start:end],
    )


def prepare():
    tree = read_json(TREE_SOURCE)
    legacy = build_skeleton(read_json(SOURCE))
    baseline = build_curriculum_tree(tree, legacy)
    matches, missing = match_courses(baseline)
    candidate_tree = copy.deepcopy(tree)
    for group in candidate_tree["course_groups"]:
        for course in group["courses"]:
            if not course.get("internal_key"):
                continue
            identifier = (
                baseline["nodes"][0]["properties"]["id"]
                + ":COURSE:INTERNAL:"
                + course["internal_key"]
            )
            match = matches.get(identifier)
            if match:
                course.update(
                    course_code=match["course_code"],
                    course_code_status="verified_hmu_public_listing",
                    year=match["year"],
                    year_status="verified_hmu_lms_year_listing",
                )
    source_record = {
        "source": PROGRAM_URL,
        "scope": "Mã học phần và năm học được đối chiếu từ danh mục LMS HMU công khai; chưa có đề cương nội dung môn.",
        "status": "public_source_checked_current_program_applicability_pending",
    }
    if source_record not in candidate_tree["source_records"]:
        candidate_tree["source_records"].append(source_record)
    candidate_tree["known_limitations"] = [
        "Giữ nguyên tên trong danh sách người dùng; tên và mã trên LMS được lưu kèm bằng chứng riêng.",
        "Đã đối chiếu mã và năm học từ danh mục công khai trên LMS cho 27 môn. Các môn mới vẫn chưa có tín chỉ trong nguồn đã đọc.",
        "Chưa truy cập được đề cương, chuẩn đầu ra học phần hoặc bài giảng của 27 môn vì trang bài học yêu cầu đăng nhập.",
        "internal_key là định danh kỹ thuật ổn định, không phải mã môn chính thức.",
        "Ngoại ngữ là yêu cầu chứng chỉ. PLO3 xác nhận mức bậc 4/6 nhưng không xác nhận người học đã hoàn thành.",
        "Mục tiêu và PLO trên LMS thuộc cấp chương trình. Số và ngày quyết định trên trang còn trống; chưa xác nhận áp dụng cho khóa của người dùng.",
    ]
    graph = build_curriculum_tree(candidate_tree, legacy)
    root_id, program_id = graph["nodes"][0]["properties"]["id"], graph["curriculum_id"]
    source_ids, evidences, counts = {}, [], {}

    def source(name):
        if name in source_ids:
            return source_ids[name]
        meta = read_json(CACHE / (name + ".json"))
        validate_hmu_url(meta["url"])
        if (
            meta.get("http_status") != 200
            or not meta.get("file")
            or digest(CACHE / meta["file"]) != meta["sha256"]
        ):
            raise ValueError("hmu_source_not_readable")
        identifier = root_id + ":HMU:SOURCE:" + fingerprint(meta["url"])[:20]
        source_ids[name] = identifier
        graph["nodes"].append(
            {
                "type": "CurriculumSource",
                "properties": {
                    "id": identifier,
                    "curriculum_id": program_id,
                    "name": meta.get(
                        "title",
                        {
                            "lms-program": "Chương trình BSNT Ngoại khoa — HMU",
                            "lms-year1": "Danh mục học phần năm thứ nhất — HMU",
                            "lms-year2-all": "Danh mục học phần năm thứ hai — HMU",
                            "lms-year3-all": "Danh mục học phần năm thứ ba — HMU",
                        }.get(name, name),
                    ),
                    "publisher": "Trường Đại học Y Hà Nội",
                    "url": meta["url"],
                    "snapshot_sha256": meta["sha256"],
                    "fetched_at_utc": meta["fetched_at_utc"],
                    "snapshot_path": (CACHE / meta["file"])
                    .relative_to(ROOT)
                    .as_posix(),
                    "review_status": "public_source_read",
                    "current_program_confirmed": False,
                },
            }
        )
        add_edge("HAS_SOURCE", root_id, identifier)
        return identifier

    def add_edge(kind, left, right):
        identifier = "HMU_EDGE:" + fingerprint([kind, left, right])[:28]
        row = {
            "type": kind,
            "from_id": left,
            "to_id": right,
            "properties": {
                "id": identifier,
                "curriculum_id": program_id,
                "hmu_batch": "HMU_PUBLIC_20261104",
            },
        }
        if not any(e["properties"]["id"] == identifier for e in graph["edges"]):
            graph["edges"].append(row)

    def statement(kind, code, name, evidence, source_name, relation, **extra):
        validate_evidence(evidence)
        evidences.append(evidence)
        identifier = root_id + ":HMU:" + kind + ":" + code
        graph["nodes"].append(
            {
                "type": kind,
                "properties": {
                    "id": identifier,
                    "curriculum_id": program_id,
                    "name": name,
                    "text": " ".join(evidence["quote"].split()),
                    "evidence_json": json.dumps(
                        evidence, ensure_ascii=False, sort_keys=True
                    ),
                    "review_status": "source_transcribed",
                    "scope": "program",
                    "current_program_confirmed": False,
                    **extra,
                },
            }
        )
        add_edge(relation, root_id, identifier)
        add_edge("SUPPORTED_BY", identifier, source(source_name))
        counts[kind] = counts.get(kind, 0) + 1
        return identifier

    program_html, _ = load_html("lms-program")
    blocks = program_sections(program_html)
    begin = next(i for i, b in enumerate(blocks) if b["text"] == "Mục tiêu chung")
    finish = next(
        i for i, b in enumerate(blocks) if b["text"].startswith("2. Chuẩn đầu ra")
    )
    objective_indices = [
        i
        for i in range(begin + 1, finish)
        if blocks[i]["tag"] == "p" and blocks[i]["text"] != "Mục tiêu cụ thể"
    ]
    for order, index in enumerate(objective_indices, 1):
        ev = make_evidence(
            "lms-program",
            {"kind": "program_block", "index": index},
            blocks[index]["text"],
        )
        statement(
            "CurriculumObjective",
            str(order),
            "Mục tiêu chung" if order == 1 else f"Mục tiêu cụ thể — đoạn {order - 1}",
            ev,
            "lms-program",
            "HAS_OBJECTIVE",
            display_order=order,
        )
    plo_ids = {}
    pages = [p.extract_text() for p in PdfReader(CACHE / "lms-attachment-1.pdf").pages]
    for row in extract_plos(pages):
        code = row["code"]
        ev = pdf_evidence(
            "lms-attachment-1",
            row["page"],
            pages[row["page"] - 1],
            row["start"],
            row["end"],
        )
        plo_ids[code] = statement(
            "CurriculumOutcome",
            code,
            code,
            ev,
            "lms-attachment-1",
            "HAS_PROGRAM_OUTCOME",
            outcome_code=code,
            competency_domain=row["domain"],
        )
    if set(plo_ids) != {f"PLO{i}" for i in range(1, 18)}:
        raise ValueError("hmu_plo_sequence_incomplete")
    for attachment, kind, relation, start_pattern in [
        (
            2,
            "CurriculumCareerPath",
            "HAS_CAREER_PATH",
            r"(?m)^(?:-\s+|Nghiên cứu viên)",
        ),
        (3, "CurriculumStudyPath", "HAS_STUDY_PATH", r"(?m)^(?:-\s+|Tiến sĩ y khoa)"),
        (
            4,
            "CurriculumReference",
            "REFERENCES_FRAMEWORK",
            r"(?m)^(?:−\s+|Khung năng lực đào tạo bác sĩ nội trú Ngoại khoa Singapore)",
        ),
    ]:
        source_name = f"lms-attachment-{attachment}"
        text = PdfReader(CACHE / (source_name + ".pdf")).pages[0].extract_text()
        starts = list(re.finditer(start_pattern, text))
        for order, match in enumerate(starts, 1):
            end = starts[order].start() if order < len(starts) else len(text)
            section = re.search(r"(?m)^5\.2\.\s*", text[match.end() : end])
            if section:
                end = match.end() + section.start()
            ev = pdf_evidence(source_name, 1, text, match.start(), end)
            name = " ".join(ev["quote"].lstrip("-− ").split())
            statement(
                kind, str(order), name, ev, source_name, relation, display_order=order
            )
    detail_rows = []
    for node in list(graph["nodes"]):
        row = matches.get(node["properties"]["id"])
        if not row:
            continue
        ev = make_evidence(
            row["snapshot"],
            {"kind": "course_title", "lms_course_id": row["lms_course_id"]},
            row["title"],
        )
        validate_evidence(ev)
        evidences.append(ev)
        p = node["properties"]
        p.update(
            hmu_lms_course_id=row["lms_course_id"],
            hmu_course_title=row["title"],
            hmu_course_url=f"https://lms.hmu.edu.vn/course/view.php?id={row['lms_course_id']}",
            hmu_listing_evidence_json=json.dumps(
                ev, ensure_ascii=False, sort_keys=True
            ),
            hmu_listing_status="verified_public_listing",
        )
        add_edge("HAS_SOURCE", p["id"], source(row["snapshot"]))
        info_name = f"course-{row['lms_course_id']}-info"
        info_meta = read_json(CACHE / (info_name + ".json"))
        info_rows = []
        if (
            info_meta.get("file")
            and not info_meta.get("redirected_to_login")
            and info_meta.get("http_status") == 200
        ):
            info_text, _ = load_html(info_name)
            info_rows = course_listings(info_text)
        own = next(
            (r for r in info_rows if r["lms_course_id"] == row["lms_course_id"]), None
        )
        summary = own["summary"] if own else ""
        view = read_json(CACHE / f"course-{row['lms_course_id']}-view.json")
        access = (
            "login_required" if view.get("redirected_to_login") else "not_confirmed"
        )
        p["hmu_lesson_access"] = access
        detail_rows.append(
            {
                "node_id": p["id"],
                "name": p["name"],
                "course_code": row["course_code"],
                "summary": summary,
                "lesson_access": access,
            }
        )
        if (
            summary
            and len(summary) > 160
            and normalized_name(summary) != normalized_name(row["course_name"])
        ):
            ev = make_evidence(
                info_name,
                {"kind": "course_summary", "lms_course_id": row["lms_course_id"]},
                summary,
            )
            sid = statement(
                "CurriculumCourseDescription",
                row["lms_course_id"],
                p["name"] + " — mô tả công khai",
                ev,
                info_name,
                "HAS_DESCRIPTION",
            )
            add_edge("HAS_DESCRIPTION", p["id"], sid)
    requirement = next(
        n for n in graph["nodes"] if n["type"] == "CurriculumRequirement"
    )
    add_edge("HAS_SOURCE", requirement["properties"]["id"], source("lms-attachment-1"))
    requirement["properties"]["hmu_supporting_program_outcome"] = "PLO3"
    summary = {
        "graph_fingerprint": fingerprint(graph),
        "baseline_graph_fingerprint": fingerprint(baseline),
        "candidate_tree_fingerprint": fingerprint(candidate_tree),
        "evidence_fingerprint": fingerprint(evidences),
        "publisher_scope": "HMU_only",
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "statement_counts": counts,
        "sources": len(source_ids),
        "courses_matched": len(matches),
        "new_course_codes": sum(
            1
            for n in baseline["nodes"]
            if n["type"] == "Course"
            and not n["properties"].get("course_code")
            and n["properties"]["id"] in matches
        ),
        "courses_without_matching_public_listing": missing,
        "course_access": detail_rows,
        "current_program_confirmed": False,
        "decision_metadata_status": "number_and_date_blank_on_public_program_page",
        "legacy_curriculum_sha256": digest(SOURCE),
        "baseline_tree_sha256": digest(TREE_SOURCE),
    }
    for name, value in [
        ("baseline-graph.json", baseline),
        ("candidate-tree.json", candidate_tree),
        ("graph.json", graph),
        ("evidence.json", evidences),
        ("summary.json", summary),
    ]:
        write_json(OUT / name, value)
    write_review()
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in {"course_access", "courses_without_matching_public_listing"}
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def apply_to_neo4j(apply=False):
    from dotenv import dotenv_values
    from neo4j import GraphDatabase

    graph = read_json(OUT / "graph.json")
    baseline = read_json(OUT / "baseline-graph.json")
    summary = read_json(OUT / "summary.json")
    candidate_tree = read_json(OUT / "candidate-tree.json")
    evidences = read_json(OUT / "evidence.json")
    if any(
        fingerprint(value) != summary[key]
        for value, key in [
            (graph, "graph_fingerprint"),
            (baseline, "baseline_graph_fingerprint"),
            (candidate_tree, "candidate_tree_fingerprint"),
            (evidences, "evidence_fingerprint"),
        ]
    ):
        raise ValueError("prepared_hmu_artifacts_changed")
    current_tree_hash = digest(TREE_SOURCE)
    if (
        current_tree_hash
        not in {summary["baseline_tree_sha256"], digest(OUT / "candidate-tree.json")}
        or digest(SOURCE) != summary["legacy_curriculum_sha256"]
    ):
        raise ValueError("hmu_curriculum_inputs_changed")
    for evidence in evidences:
        validate_evidence(evidence)
    for node in graph["nodes"]:
        props = node["properties"]
        for key in ["evidence_json", "hmu_listing_evidence_json"]:
            if key in props:
                ev = json.loads(props[key])
                validate_evidence(ev)
                if key == "evidence_json" and props["text"] != " ".join(
                    ev["quote"].split()
                ):
                    raise ValueError("hmu_statement_changed_from_source")
    config = dotenv_values(ROOT / ".env", interpolate=False, encoding="utf-8-sig")
    backup = (
        ROOT
        / "data/backups/hmu-curriculum"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
    )
    with (
        GraphDatabase.driver(
            config["NEO4J_URI"],
            auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
            connection_timeout=5,
            connection_acquisition_timeout=10,
            max_transaction_retry_time=0,
        ) as driver,
        driver.session(database=config["NEO4J_DATABASE"]) as session,
    ):
        with session.begin_transaction(timeout=90) as tx:
            before = read_graph(tx, None)
            plan = build_plan(graph, before, baseline)
            report = {
                "status": "preflight_passed",
                "nodes_to_create": plan["nodes_to_create"],
                "nodes_to_update": plan["nodes_to_update"],
                "edges_to_create": plan["edges_to_create"],
                "edges_to_delete": plan["edges_to_delete"],
            }
            if plan["edges_to_delete"]:
                raise ValueError("hmu_supplement_must_not_delete_relationships")
            if not apply:
                write_json(OUT / "preflight.json", report)
                return report
            write_json(backup / "before-all.json", before)
            write_json(backup / "plan.json", plan)
            write_json(backup / "curriculum-tree-before.json", read_json(TREE_SOURCE))
            write_graph(tx, plan, LABELS | EXTRA_LABELS, RELATIONS | EXTRA_RELATIONS)
            after = read_graph(tx, None)
            verification = verify_graph(graph, before, after, plan, baseline)
            tx.commit()
        with session.begin_transaction(timeout=60) as tx:
            after = read_graph(tx, None)
            verification = verify_graph(graph, before, after, plan, baseline)
    write_json(TREE_SOURCE, candidate_tree)
    write_json(backup / "after-all.json", after)
    report.update(
        verification,
        status="imported_and_verified",
        expert_verified=False,
        current_program_confirmed=False,
    )
    write_json(backup / "report.json", report)
    target = (
        "import-report.json"
        if plan["nodes_to_create"] or plan["nodes_to_update"] or plan["edges_to_create"]
        else "verification.json"
    )
    write_json(OUT / target, report)
    write_review()
    return report


def write_review():
    summary = read_json(OUT / "summary.json")
    write_material_review(OUT)
    (OUT / "view.cypher").write_text(
        "// Newly added HMU evidence, objectives and programme outcomes.\n"
        "MATCH p=()-[r]->() WHERE r.hmu_batch='HMU_PUBLIC_20261104' RETURN p;\n\n"
        "// Programme outcomes with their PDF sources.\n"
        "MATCH p=(:Curriculum)-[:HAS_PROGRAM_OUTCOME]->(:CurriculumOutcome)-[:SUPPORTED_BY]->(:CurriculumSource) RETURN p;\n\n"
        "// Course codes confirmed on the public HMU LMS.\n"
        "MATCH (c:Course) WHERE c.hmu_listing_status='verified_public_listing' RETURN c.course_code AS ma, c.name AS mon, c.hmu_course_url AS url, c.content_status AS noi_dung ORDER BY c.course_code;\n",
        encoding="utf-8",
    )
    imported = (OUT / "import-report.json").exists()
    lines = [
        "# Bổ sung Curriculum từ nguồn công khai HMU — 04/11/2026",
        "",
        "Trạng thái: "
        + (
            "đã nhập và đọc lại Neo4j để kiểm chứng."
            if imported
            else "đã chuẩn bị, chưa nhập Neo4j."
        ),
        "",
        "- 8 nguồn, toàn bộ có URL thuộc `lms.hmu.edu.vn`: trang chương trình, danh mục 3 năm và 4 PDF đính kèm.",
        f"- Đối chiếu {summary['courses_matched']} môn; bổ sung {summary['new_course_codes']} mã trước đây chưa có. Giữ nguyên ID môn.",
        "- 7 đoạn mục tiêu (1 mục tiêu chung và 6 đoạn mục tiêu cụ thể), 17 chuẩn đầu ra cấp chương trình (PLO1–PLO17).",
        "- 3 vị trí việc làm, 2 hướng học tiếp và 7 mục khung/chương trình tham khảo được HMU liệt kê. Không thu thập nội dung từ các trường hoặc tổ chức ngoài HMU.",
        "- Mỗi phát biểu có URL, thời điểm thu thập, hash snapshot và vị trí đoạn HTML hoặc trang/khoảng ký tự PDF; trích dẫn được kiểm lại trước khi ghi.",
        "",
        "## Phần còn thiếu",
        "",
        "Cả 27 trang bài học chuyển tới đăng nhập. Mô tả công khai chỉ là tên/tóm tắt rất ngắn; chưa bổ sung đề cương, nội dung bài giảng hoặc chuẩn đầu ra riêng của môn. Các môn giữ trạng thái chờ nội dung giáo viên.",
        "Số và ngày quyết định trên trang chương trình còn trống. Ghi nhận đây là nội dung công khai của HMU; chưa xác nhận áp dụng cho khóa của người dùng, chưa được chuyên gia phê duyệt.",
        "Các PDF Google Drive từ trang SĐH cũ không được dùng: chủ sở hữu không cho tải. Bộ bổ sung dùng 4 PDF công khai đính kèm trực tiếp trên LMS, đã đọc và xem 5 trang PDF.",
        "",
        "## Xem và kiểm chứng",
        "",
        "- [Danh mục xin tài liệu học tập chính thức gửi giảng viên](review.html).",
        "- [Truy vấn Neo4j](view.cypher).",
        "- [Kết quả nhập](import-report.json) · [Kiểm tra chạy lại](verification.json).",
        "- [Graph có nguồn](graph.json) · [Trích dẫn](evidence.json) · [Danh sách nguồn và giới hạn](summary.json).",
        "- Snapshot DB trước/sau được lưu riêng trong `data/backups/hmu-curriculum/`.",
        "- 14 kiểm tra tự động liên quan đã qua; kiểm riêng việc giữ định danh, bảo toàn dữ liệu có trước, nguồn HMU, trích dẫn và PLO qua trang.",
        "",
        "Không gọi LLM, không OCR lại sách và không tạo phát biểu chuyên môn y khoa từ tên môn.",
    ]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.collect:
            collect()
        if args.prepare:
            prepare()
        print(json.dumps(apply_to_neo4j(args.apply), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 -- never print credentials or driver tracebacks
        reason = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc))
            else None
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "reason": reason,
                    "error_code": getattr(exc, "code", None),
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
