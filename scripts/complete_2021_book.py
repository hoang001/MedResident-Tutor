"""Resume remaining 2021 book source review with auditable, resumable LLM jobs.

Uses the repository .env directly. No credential fallback, HTTP retries, response
deadline, changes to raw sources, or automatic schema/Neo4j migrations.
"""

import argparse
import base64
import copy
import difflib
import hashlib
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import Settings
from document_toolkit.llm_client import parse_json_response
from knowledge_pipeline.kg_v2.corrections import trace_raw
from scripts.review_2021_book import OUT as PREVIOUS
from scripts.review_2021_book import PDF, ROOT, SOURCE, inputs

OUT = ROOT / "data/knowledge-extraction/v2/source-review-20261102-2021-completion"

VISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["edits", "uncertain_lines", "image_readable"],
    "properties": {
        "edits": {
            "type": "array",
            "maxItems": 80,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["line", "before", "after", "reason"],
                "properties": {
                    "line": {"type": "integer", "minimum": 0},
                    "before": {"type": "string", "minLength": 1, "maxLength": 160},
                    "after": {"type": "string", "maxLength": 160},
                    "reason": {"type": "string", "maxLength": 120},
                },
            },
        },
        "uncertain_lines": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
        },
        "image_readable": {"type": "boolean"},
    },
}

CONFIRM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["confirmed", "rejected", "unreadable_lines"],
    "properties": {
        "confirmed": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "rejected": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["edit", "original_correct", "printed"],
                "properties": {
                    "edit": {"type": "integer", "minimum": 0},
                    "original_correct": {"type": "boolean"},
                    "printed": {"type": ["string", "null"], "maxLength": 200},
                },
            },
        },
        "unreadable_lines": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
        },
    },
}

VISION_PROMPT = """Bạn đối chiếu OCR với ẢNH TRANG SÁCH được cung cấp, không dùng kiến thức y khoa để viết lại sách.
Đầu vào OCR đánh số dòng từ 0. Chỉ sửa lỗi ký tự/từ mà ảnh đọc được rõ ràng. Giữ nguyên thứ tự, nội dung, phủ định, điều kiện, số liệu và đơn vị thực sự in trên ảnh.
Trả duy nhất JSON: {"edits":[{"line":0,"before":"chuỗi con chính xác của dòng OCR","after":"chuỗi đúng trên ảnh","reason":"lỗi OCR nào"}],"uncertain_lines":[0],"image_readable":true}.
before nên là cụm từ ngắn nhất đủ ngữ cảnh (2-8 từ), không chép cả đoạn nếu không cần. Mỗi cụm phải xuất hiện trong đúng dòng, không xuất hiện trong dòng khác để đoán. Nếu một cụm lặp trong cùng dòng, chỉ đề xuất nếu TẤT CẢ lần xuất hiện trên dòng đều cần sửa như nhau.
Không sửa lỗi tác giả, không hiện đại hóa điều trị, không thay biệt ngữ chỉ vì khác thói quen. Nếu ảnh và OCR cùng ghi một số liệu bất thường thì GIỮ số liệu đó. Nếu không đọc chắc, ghi dòng vào uncertain_lines, không đoán. Không thêm phần bị thiếu ngoài khung ảnh. Không sửa hoặc gộp số hiệu Câu, Bài, bảng/hình. Không chuyển bảng thành văn xuôi; chỉ sửa chữ trong từng dòng/cell. Không thay dấu +,-,<,>,đơn vị hoặc chữ Không/Chưa trừ khi ảnh cho thấy rõ lỗi OCR. Những thay đổi số liệu/phủ định sẽ cần bước kiểm tra riêng.
Không đề xuất sửa những dòng chỉ là header/footer, tên tác giả, số trang hay lời mô tả ảnh của OCR. Ưu tiên sửa từ y khoa biến nghĩa: bỏng/bóng, gãy/gây, hở/hông, tủy/tụy, mủ/mù/mũ, cân/cần, chày/chân, đùi/dài/dùi, chỏm/chòm, mấu/máu, duỗi/đuôi, dải/dài, vạt/vật, chỉnh/chính, lồi/lời, xốp/xấp/khớp, néo/nẹp. Những từ này vẫn có thể đúng ở ngữ cảnh khác; chỉ thay khi ĐỌC ĐƯỢC trên ảnh.
"""

NODE_PROMPT = """Bạn đối chiếu bản nháp knowledge graph với NGUỒN SÁCH đã đánh số dòng. Chỉ làm biên tập trung thành với nguồn, không dùng kiến thức ngoài sách để bổ sung hay hiện đại hóa điều trị.
Mỗi proposal phải có một quyết định. Trả duy nhất JSON {"nodes":[{"key":"N1","action":"keep|correct|merge|reject","type":"Condition","name":"tên chính xác/có căn cứ trong nguồn","merge_into":null,"ranges":[[8,12,15]],"parent":null,"kind":null,"reason":"lý do ngắn cụ thể"}]}.
ranges là [trang PDF, dòng đầu, dòng cuối] (0-based, hai đầu inclusive), phải có nội dung mô tả thực sự, đầy đủ điều kiện/phủ định; không chỉ tên hoặc tiêu đề. Có thể trích thêm dòng trong CHÍNH BÀI này để khôi phục nội dung thiếu. Không viết lại mô tả; chương trình sẽ lấy nguyên văn các dòng đó. Không trích header/footer, tác giả, tài liệu tham khảo, lời mô tả ảnh OCR như bằng chứng y khoa.
Các type duy nhất: Condition, Anatomy, Finding, Classification, ClassificationCategory, DiagnosticMethod, Intervention, Drug, ClinicalPrinciple, Skill, SampleQuestion. Một vi khuẩn, độc tố, tai nạn hoặc dụng cụ (đinh, nẹp, vít, chỉ, khung thuần vật thể) không được ép vào Condition/Drug/Intervention. Có thể giữ QUY TRÌNH cố định ngoài/đóng đinh như Intervention nếu nguồn nói rõ thao tác. Reject bản thân dụng cụ nếu ontology không biểu diễn được. Nội dung của nó vẫn nằm trong node chủ đề chương.
ClinicalPrinciple phải là nguyên tắc có tính quy phạm thật trong nguồn, không phải công thức/cơ chế bệnh sinh hay tiêu đề. Skill chỉ từ mục tiêu học tập/yêu cầu/thao tác có căn cứ rõ; kind=cognitive hoặc practical, không suy ra kỹ năng từ câu hỏi hay tự coi người học đã làm được thao tác. Câu hỏi sẽ được dựng lại nguyên văn từ phần question, không tự tạo đáp án.
ClassificationCategory cần parent là key Classification đúng có bằng chứng. Không trộn Độ I của hệ này với hệ khác. Thuộc tính cha phải được nêu bằng tên và dòng phạm vi hệ phân loại; không gán chỉ vì gần nhau.
Trong cùng bài, các proposal cùng khái niệm/loại và cùng ngữ nghĩa nguồn nên merge về một key; KHÔNG gộp chỉ vì giống tên ngắn nhưng khác phạm vi. merge_into phải là key khác trong input, không vòng lặp. Ưu tiên key đang có trong Neo4j (already_imported=true) khi thực sự tương đương, và giữ tất cả nội dung/nguồn khác nhau trong canonical. Không gộp các bệnh khác nhau. Một Điều trị bảo tồn cho bệnh A không gộp với bệnh B dù trùng tên.
Chỉnh tên OCR dựa trên văn bản nguồn đã đối chiếu ảnh, không đoán tên mới. Nếu tên chưa rõ hoặc khái niệm không đủ căn cứ thì reject với lý do. Node có nguồn mô tả lành/ác tính, nguy cơ, chẩn đoán phân biệt không có nghĩa là cho phép tự suy ra quan hệ nhân quả.
Tên được giữ hoặc sửa cần trích được trong các dòng ranges (cho phép chuẩn hóa dấu câu/cách viết hoa). Với category có thể dùng tên ngắn đúng nguồn, chương trình tự thêm tên parent để tránh nhầm. Đừng trả nguyên đoạn làm name trừ Skill là mục tiêu học tập thực sự. Đừng viết phần giải thích bên ngoài JSON.
canonical_priority chỉ là thứ tự chọn đại diện để tránh merge vòng: merge_into phải có canonical_priority NHỎ HƠN key hiện tại. Key nhỏ nhất của một nhóm tương đương phải keep/correct. chapter_node_index cho phép tìm key ở nhóm khác trong cùng bài; chỉ ra quyết định cho danh sách nodes được yêu cầu. is_chapter_root là chủ đề y khoa có trong tiêu đề/nội dung bài; có thể gộp về concept tương đương đã có, và chương trình sẽ giữ nội dung nguồn của cả bài tại đại diện đó.
"""

EDGE_PROMPT = """Đối chiếu từng quan hệ nháp với nguyên văn nguồn của bài. Chỉ giữ khi ý nghĩa, chiều và điều kiện có bằng chứng trực tiếp.
Trả duy nhất JSON {"edges":[{"key":"E1","action":"keep|correct|reject","from_key":"N1","to_key":"N2","type":"MANAGED_BY","condition":null,"ranges":[[8,10,12]],"reason":"lý do cụ thể"}]}.
Mỗi input key phải có quyết định. Không tạo node mới. Sửa chiều/loại chỉ khi nguồn nói rõ quan hệ thật; nếu không biểu diễn được thì reject, nội dung vẫn ở node chủ đề chương.
IS_A = subtype -> supertype, KHÔNG part-of. LOCATED_IN Condition->Anatomy. HAS_FINDING Condition->Finding. CLASSIFIED_BY Condition->Classification. HAS_CATEGORY Classification->ClassificationCategory. EVALUATED_BY Condition->DiagnosticMethod. MANAGED_BY Condition->Intervention. USES_DRUG Intervention->Drug. MAY_CAUSE Condition/Intervention->Condition (nhân quả/biến chứng thật). GUIDED_BY Condition/Intervention->ClinicalPrinciple. APPLIES_TO và REQUIRES_KNOWLEDGE_OF Skill->medical. ABOUT SampleQuestion->medical. ASSESSES SampleQuestion->Skill. HAS_SUBSKILL Skill->Skill.
Không dùng MAY_CAUSE cho chẩn đoán phân biệt, bệnh kèm theo, chống chỉ định, nguyên nhân chưa rõ, một yếu tố nguy cơ đơn thuần. Không coi chống chỉ định là chỉ định, không đổi 'không', 'chưa', 'chỉ khi', 'có thể', 'nếu' thành khẳng định. Không bỏ tuổi, loại gãy, giai đoạn, mức độ, ngoại lệ hoặc điều kiện sau mổ.
Một tiêu đề hoặc câu hỏi nhắc hai tên không đủ chứng minh quan hệ lâm sàng. Không suy chỉ định điều trị từ tiêu đề 'Điều trị'. Trích paragraph/dòng đầy đủ, không cắt để bỏ phủ định. Không nhập quan hệ không đọc chắc từ nguồn.
condition mô tả điều kiện áp dụng trong nguồn, không tự điền số liệu. ranges phải là [PDF page,first_line,last_line] inclusive 0-based trong đúng bài. Không viết lại nội dung nguồn. Đầu ra JSON, không Markdown hoặc bình luận.
"""


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    original, pages, _, plan = inputs()
    for line in (
        (PREVIOUS / "combined/audit/pages.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        p = json.loads(line)
        pages[p["pdf_page"]] = p
    baseline = OUT / "audit/protected-hashes.json"
    if not baseline.exists():
        protected = read_json(PREVIOUS / "audit/protected-hashes.json")
        for p in PREVIOUS.rglob("*"):
            if p.is_file():
                protected[p.relative_to(ROOT).as_posix()] = hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
        write_json(baseline, protected)
    if not (OUT / "audit/input-pages.jsonl").exists():
        jsonl(OUT / "audit/input-pages.jsonl", [pages[k] for k in sorted(pages)])
        write_json(OUT / "audit/input-graph.json", original)
        write_json(OUT / "audit/plan.json", plan)
        write_json(
            OUT / "audit/missing-extraction.json",
            read_json(PREVIOUS / "missing-extraction.json"),
        )
    if not (OUT / "audit/neo4j-before-all.json").exists():
        from dotenv import dotenv_values
        from neo4j import GraphDatabase

        from knowledge_pipeline.neo4j_export import read_graph

        env = dotenv_values(ROOT / ".env", interpolate=False)
        with (
            GraphDatabase.driver(
                env["NEO4J_URI"],
                auth=(env["NEO4J_USERNAME"], env["NEO4J_PASSWORD"]),
                connection_timeout=10,
                max_transaction_retry_time=0,
            ) as driver,
            driver.session(database=env["NEO4J_DATABASE"]) as session,
            session.begin_transaction(timeout=30) as tx,
        ):
            snapshot = read_graph(tx, None)
        write_json(OUT / "audit/neo4j-before-all.json", snapshot)
    print(
        json.dumps(
            {
                "stage": "prepared",
                "pages": len(pages),
                "nodes": len(original["nodes"]),
                "chapters": len(plan["chapters"]),
            }
        ),
        flush=True,
    )


def page_inputs():
    return {
        p["pdf_page"]: p
        for p in map(
            json.loads,
            (OUT / "audit/input-pages.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }


def source_inventory():
    """Index every original proposal, including malformed records, without approval."""
    graph, original_pages, _, plan = inputs()
    windows = read_json(SOURCE / "audit/windows.json")
    blocks = {b["block_id"]: b for w in windows for b in w["blocks"]}
    mappings = read_json(SOURCE / "audit/draft-id-mapping.json")
    identity = {
        (r["window_id"], r["local_id"]): mappings.get(r["candidate_id"])
        for r in read_json(SOURCE / "audit/identity_registry.json")
    }
    keys = {n["id"]: f"N{i}" for i, n in enumerate(graph["nodes"])}
    nodes = {
        f"N{i}": {"key": f"N{i}", "graph": n, "raw": [], "ranges": []}
        for i, n in enumerate(graph["nodes"])
    }
    aliases = {}
    raw_edges = []

    def ranges(sources):
        result = []
        if not isinstance(sources, list):
            return result
        for s in sources:
            if not isinstance(s, dict):
                continue
            b = blocks.get(s.get("block_id"))
            if not b:
                continue
            p = original_pages[b["pdf_page"]]
            lo = p["text"].count("\n", 0, b["char_start"])
            hi = p["text"].count("\n", 0, max(b["char_start"], b["char_end"] - 1))
            r = [b["pdf_page"], lo, hi]
            if r not in result:
                result.append(r)
        return result

    def collect(wid, row, kind):
        if not isinstance(row, dict):
            return
        if kind == "edge":
            raw_edges.append({"window_id": wid, "candidate": row})
            return
        lid = row.get("local_id")
        if not isinstance(lid, str):
            return
        identifier = identity.get((wid, lid))
        key = keys.get(identifier) or "X_" + fingerprint([wid, lid])[:24]
        aliases[(wid, lid)] = key
        item = nodes.setdefault(
            key, {"key": key, "graph": None, "raw": [], "ranges": []}
        )
        raw_record = {"window_id": wid, "candidate": row}
        if raw_record not in item["raw"]:
            item["raw"].append(raw_record)
        ss = []
        for field in ["identity_sources", "basis_sources", "sources"]:
            if isinstance(row.get(field), list):
                ss += row[field]
        for c in row.get("content") or []:
            if isinstance(c, dict) and isinstance(c.get("sources"), list):
                ss += c["sources"]
        for r in ranges([s for s in ss if isinstance(s, dict)]):
            if r not in item["ranges"]:
                item["ranges"].append(r)

    for w in windows:
        wid = w["window_id"]
        path = SOURCE / "audit/raw" / f"{wid}.json"
        if path.exists():
            raw = read_json(path)
            for n in raw["nodes"]:
                collect(wid, n, "node")
            for e in raw["edges"]:
                collect(wid, e, "edge")
    for path in sorted((OUT / "reextracted").glob("WINDOW*.json")):
        result = read_json(path)
        wid = result["window_id"]
        for n in result["raw"]["nodes"]:
            collect(wid, n, "node")
        for e in result["raw"]["edges"]:
            collect(wid, e, "edge")
        for rejected in result["invalid_records"]:
            collect(wid, rejected["candidate"], rejected["kind"])
    for fn in ["review-items.jsonl", "rejected-items.jsonl"]:
        for line in (SOURCE / fn).read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            candidate = r.get("candidate")
            if isinstance(candidate, dict):
                collect(
                    r.get("window_id"),
                    candidate,
                    "edge" if "from_id" in candidate else "node",
                )
    # Every graph node has its own source references even if raw identity was held.
    old_locs = {r["locator_id"]: r for r in read_json(SOURCE / "audit/locators.json")}
    for item in nodes.values():
        if item["graph"]:
            from scripts.review_2021_book import refs

            for s in refs(item["graph"]):
                loc = old_locs[s["locator_id"]]
                p = original_pages[loc["pdf_page"]]
                r = [
                    loc["pdf_page"],
                    p["text"].count("\n", 0, loc["char_start"]),
                    p["text"].count(
                        "\n", 0, max(loc["char_start"], loc["char_end"] - 1)
                    ),
                ]
                if r not in item["ranges"]:
                    item["ranges"].append(r)
        chapters = {
            c["lesson_number"]
            for c in plan["chapters"]
            for p, _, _ in item["ranges"]
            if c["pdf_pages"]["start"] <= p <= c["pdf_pages"]["end"]
        }
        if not chapters:
            by_window = {w["window_id"]: w for w in windows}
            for raw in item["raw"]:
                window = by_window.get(raw["window_id"], {})
                match = re.search(r"2021-bai-(\d+)", window.get("key", ""))
                if match:
                    chapters.add(int(match.group(1)))
        item["chapter"] = next(iter(chapters)) if len(chapters) == 1 else None
    for chapter in plan["chapters"]:
        number = chapter["lesson_number"]
        title = chapter["title"]
        kind = "Intervention" if title.startswith("Điều trị ") else "Condition"
        name = re.sub(r"^Đại cương\s+", "", title)
        if name:
            name = name[0].upper() + name[1:]
        rr = []
        for b in blocks.values():
            if (
                chapter["pdf_pages"]["start"]
                <= b["pdf_page"]
                <= chapter["pdf_pages"]["end"]
            ):
                for r in ranges([{"block_id": b["block_id"]}]):
                    if r not in rr:
                        rr.append(r)
        key = f"B{number:02d}"
        nodes[key] = {
            "key": key,
            "graph": None,
            "chapter": number,
            "is_chapter_root": True,
            "raw": [{"window_id": None, "candidate": {"name": name, "type": kind}}],
            "ranges": rr,
        }
    unique_edges = {}
    for i, e in enumerate(graph["edges"]):
        unique_edges[f"E{i}"] = {
            "key": f"E{i}",
            "graph": e,
            "from_key": keys[e["from_id"]],
            "to_key": keys[e["to_id"]],
            "raw": [],
            "ranges": [],
        }
        for s in e["sources"]:
            loc = old_locs[s["locator_id"]]
            p = original_pages[loc["pdf_page"]]
            unique_edges[f"E{i}"]["ranges"].append(
                [
                    loc["pdf_page"],
                    p["text"].count("\n", 0, loc["char_start"]),
                    p["text"].count(
                        "\n", 0, max(loc["char_start"], loc["char_end"] - 1)
                    ),
                ]
            )
    # Keep raw proposals separate, then explicitly deduplicate after semantic review.
    for r in raw_edges:
        wid, row = r["window_id"], r["candidate"]
        key = "Y_" + fingerprint([wid, row])[:24]
        if key in unique_edges:
            continue
        unique_edges[key] = {
            "key": key,
            "graph": None,
            "from_key": aliases.get((wid, row.get("from_id"))),
            "to_key": aliases.get((wid, row.get("to_id"))),
            "raw": [r],
            "ranges": ranges(row.get("sources", [])),
        }
    for e in unique_edges.values():
        left = nodes.get(e["from_key"], {}).get("chapter")
        right = nodes.get(e["to_key"], {}).get("chapter")
        e["chapter"] = left if left == right else None
    write_json(
        OUT / "audit/proposals.json",
        {
            "nodes": list(nodes.values()),
            "edges": list(unique_edges.values()),
            "raw_node_aliases": [
                {"window_id": wid, "local_id": lid, "key": key}
                for (wid, lid), key in aliases.items()
            ],
        },
    )
    block_rows = []
    for b in blocks.values():
        if b["pdf_page"] < 8:
            continue
        rr = ranges([{"block_id": b["block_id"]}])
        block_rows.append(
            {
                "block_id": b["block_id"],
                "range": rr[0],
                "role": b.get("role"),
                "kind": b.get("kind"),
                "section_title": b.get("section_title"),
            }
        )
    write_json(OUT / "audit/source-block-index.json", block_rows)
    print(
        json.dumps(
            {
                "stage": "inventory",
                "nodes": len(nodes),
                "edges": len(unique_edges),
                "blocks": len(block_rows),
                "unscoped_nodes": sum(n["chapter"] is None for n in nodes.values()),
            }
        ),
        flush=True,
    )


def reextract_missing(workers=2):
    """Regenerate only the 19 explicitly missing windows, never the whole batch."""
    from knowledge_pipeline.kg_v2.contracts import schemas
    from knowledge_pipeline.kg_v2.draft_run import DRAFT_INSTRUCTION, messages_for

    missing = read_json(OUT / "audit/missing-extraction.json")["failed_windows"]
    windows = {w["window_id"]: w for w in read_json(SOURCE / "audit/windows.json")}
    raw_schema = schemas()[0]
    prompt = (
        DRAFT_INSTRUCTION
        + "\nTrả JSON đúng schema sau. Không đảo IS_A: subtype -> supertype. Chẩn đoán phân biệt, chống chỉ định, yếu tố nguy cơ, tổn thương phối hợp KHÔNG tự chuyển thành MAY_CAUSE. Không tạo Drug từ đinh/nẹp/chỉ/khung, không tạo Condition từ vi khuẩn hay tai nạn. Cite block_id thật, ưu tiên toàn block, không diễn giải lại excerpt. Không tạo tri thức ngoài đoạn nguồn.\n"
        + json.dumps(raw_schema, ensure_ascii=False)
    )

    def one(row):
        wid = row["window_id"]
        window = copy.deepcopy(windows[wid])
        corrected = OUT / "audit/corrected-pages.jsonl"
        if corrected.exists():
            new_pages = {
                p["pdf_page"]: p
                for p in map(
                    json.loads, corrected.read_text(encoding="utf-8").splitlines()
                )
            }
            _, old_pages, _, _ = inputs()
            for b in window["blocks"]:
                pn = b["pdf_page"]
                old = old_pages[pn]["text"]
                first = old.count("\n", 0, b["char_start"])
                last = old.count("\n", 0, max(b["char_start"], b["char_end"] - 1))
                lines = new_pages[pn]["text"].splitlines(keepends=True)
                b["upstream_char_start"], b["upstream_char_end"] = (
                    b["char_start"],
                    b["char_end"],
                )
                b["char_start"] = sum(map(len, lines[:first]))
                b["char_end"] = sum(map(len, lines[: last + 1]))
                while (
                    b["char_end"] > b["char_start"]
                    and new_pages[pn]["text"][b["char_end"] - 1] in "\r\n"
                ):
                    b["char_end"] -= 1
                b["text"] = new_pages[pn]["text"][b["char_start"] : b["char_end"]]
                b["correction"] = new_pages[pn]["correction"]
            window["parent_window_id"] = wid
            window["window_id"] = (
                "WINDOW2_REPAIR_"
                + fingerprint(
                    [wid, [(b["block_id"], b["text"]) for b in window["blocks"]]]
                )[:24]
            )
            write_json(OUT / f"reextracted-input/{wid}.json", window)
        response = request_job(
            "missing-" + wid,
            messages_for(window, prompt),
            max_tokens=16384,
            schema=raw_schema,
        )
        if response["status"] == "received_json":
            from knowledge_pipeline.kg_v2.recovery import project_records

            try:
                projected, rejected = project_records(response["value"], raw_schema)
                write_json(
                    OUT / f"reextracted/{wid}.json",
                    {
                        "window_id": wid,
                        "generation_window_id": window["window_id"],
                        "raw": projected,
                        "invalid_records": rejected,
                        "shard": row["shard"],
                    },
                )
            except ValueError:
                pass
        return {
            "window_id": wid,
            "status": response["status"],
            "http_status": response["http_status"],
            "seconds": response["latency_seconds"],
        }

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(one, r) for r in missing]
        for f in as_completed(futures):
            print(json.dumps(f.result()), flush=True)


def request_job(key, messages, *, max_tokens=8192, schema=None):
    """One real request per job. Completed raw outputs are never overwritten."""
    folder = OUT / "jobs" / key
    result_file = folder / "response.json"
    if result_file.exists():
        cached = read_json(result_file)
        if cached.get("input_fingerprint") != fingerprint(messages):
            raise ValueError("cached_job_input_changed_use_new_revision")
        if cached["status"] == "parse_error":
            fenced = re.findall(
                r"```(?:json)?\s*\n?(.*?)\n?```",
                cached.get("raw_content", ""),
                re.DOTALL,
            )
            if len(fenced) == 1:
                try:
                    value = json.loads(fenced[0].strip())
                    cached = copy.deepcopy(cached)
                    cached.update(
                        value=value,
                        status="received_json",
                        parse_strategy="single_complete_json_fence_extra_commentary_ignored",
                    )
                    write_json(
                        folder / "parsed.json",
                        {
                            "value": value,
                            "strategy": cached["parse_strategy"],
                            "raw_response_fingerprint": fingerprint(
                                read_json(result_file)
                            ),
                        },
                    )
                except ValueError:
                    pass
        return cached
    settings = Settings.from_env(ROOT / ".env")
    if not settings.llm_api_key or settings.llm_api_key.startswith("<"):
        raise ValueError("api_key_missing_or_placeholder")
    folder.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    report = {
        "job": key,
        "endpoint": settings.endpoint_url(settings.llm_chat_completions_endpoint),
        "model": settings.model,
        "attempts": 1,
        "response_timeout": None,
        "input_fingerprint": fingerprint(messages),
        "http_status": None,
    }
    try:
        with httpx.Client(
            trust_env=False,
            transport=httpx.HTTPTransport(retries=0),
            timeout=httpx.Timeout(None, connect=30, pool=30),
        ) as client:
            response = client.post(
                report["endpoint"],
                headers={"Authorization": "Bearer " + settings.llm_api_key},
                json={
                    "model": settings.model,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "response_format": (
                        {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "source_review",
                                "strict": True,
                                "schema": schema,
                            },
                        }
                        if schema
                        else {"type": "json_object"}
                    ),
                },
            )
        report["http_status"] = response.status_code
        safe_text = response.text.replace(settings.llm_api_key, "[REDACTED]")
        if response.status_code != 200:
            report.update(status="http_error", message=safe_text)
        else:
            body = json.loads(safe_text)
            choice = body["choices"][0]
            report.update(
                raw_content=choice["message"]["content"],
                finish_reason=choice.get("finish_reason"),
                usage=body.get("usage"),
            )
            if choice.get("finish_reason") == "length":
                report["status"] = "truncated"
            else:
                try:
                    report.update(
                        value=parse_json_response(report["raw_content"]),
                        status="received_json",
                    )
                except (ValueError, TypeError):
                    report["status"] = "parse_error"
    except Exception as exc:  # noqa: BLE001 -- errors may contain credentials
        report.update(
            status="transport_error",
            error_type=type(exc).__name__,
            message=str(exc).replace(settings.llm_api_key, "[REDACTED]"),
        )
    report["latency_seconds"] = round(time.perf_counter() - started, 3)
    write_json(result_file, report)
    return report


def render_page(pn):
    path = OUT / f"pdf/{pn}.png"
    if not path.exists():
        import pypdfium2 as pdfium

        path.parent.mkdir(parents=True, exist_ok=True)
        doc = pdfium.PdfDocument(PDF)
        doc[pn - 1].render(scale=1.6).to_pil().save(path)
        doc.close()
    return path


def render_tiles(pn):
    paths = [OUT / f"pdf/{pn}-tile-{i}.png" for i in range(3)]
    if not all(p.exists() for p in paths):
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(PDF)
        page = doc[pn - 1]
        height = page.get_height()
        for i, path in enumerate(paths):
            if path.exists():
                continue
            # Three overlapping vertical regions make small print readable.
            top = max(0, height * i / 3 - 10)
            bottom = min(height, height * (i + 1) / 3 + 10)
            path.parent.mkdir(parents=True, exist_ok=True)
            page.render(scale=2.2, crop=(0, height - bottom, 0, top)).to_pil().save(
                path
            )
        doc.close()
    return paths


def vision_page(pn, page, variant="vision-hi"):
    path = render_page(pn)
    numbered = "\n".join(
        f"{i}: {line}" for i, line in enumerate(page["text"].splitlines())
    )
    messages = [
        {"role": "system", "content": VISION_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"PDF page {pn}\nOCR:\n{numbered}"},
                *[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + base64.b64encode(tile.read_bytes()).decode()
                        },
                    }
                    for tile in render_tiles(pn)
                ],
            ],
        },
    ]
    response = request_job(f"{variant}-{pn:03d}", messages, schema=VISION_SCHEMA)
    status = response["status"]
    value = response.get("value", {})
    if (
        status == "received_json"
        and isinstance(value, dict)
        and isinstance(value.get("edits"), list)
        and isinstance(value.get("uncertain_lines"), list)
    ):
        lines = page["text"].splitlines()
        valid, rejected = [], []
        for edit in value["edits"]:
            if (
                not isinstance(edit, dict)
                or not isinstance(edit.get("line"), int)
                or not 0 <= edit["line"] < len(lines)
                or not edit.get("before")
                or not isinstance(edit.get("after"), str)
                or edit["before"] not in lines[edit["line"]]
                or "\n" in edit["after"]
            ):
                rejected.append(edit)
            elif edit["before"] != edit["after"] and not any(
                (e["line"], e["before"], e["after"])
                == (edit["line"], edit["before"], edit["after"])
                for e in valid
            ):
                valid.append(edit)
        decision = {
            "pdf_page": pn,
            "status": "image_reviewed_by_llm",
            "vision_job": response["job"],
            "input_page_fingerprint": fingerprint(page),
            "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "edits": valid,
            "rejected_edits": rejected,
            "uncertain_lines": value["uncertain_lines"],
            "image_readable": value.get("image_readable", False),
            "expert_verified": False,
        }
        write_json(OUT / f"vision/{pn:03d}.json", decision)
        status = decision["status"]
    return {
        "page": pn,
        "status": status,
        "edits": len(value.get("edits", [])) if isinstance(value, dict) else 0,
        "seconds": response.get("latency_seconds"),
        "http_status": response.get("http_status"),
    }


def repair_vision(workers=2, limit=None):
    source = page_inputs()

    def one(pn):
        row = vision_page(pn, source[pn])
        if row["status"] != "image_reviewed_by_llm":
            row = vision_page(pn, source[pn], "vision-hi-json")
        return row

    missing = [
        pn
        for pn in sorted(source)
        if pn >= 8 and not (OUT / f"vision/{pn:03d}.json").exists()
    ]
    if limit:
        missing = missing[:limit]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, pn) for pn in missing]):
            print(json.dumps(f.result()), flush=True)


def vision(pages=None, workers=2):
    source = page_inputs()
    todo = [
        p
        for p in (pages or sorted(source))
        if p >= 8
        and p in source
        and (
            not (OUT / f"vision/{p:03d}.json").exists()
            or not read_json(OUT / f"vision/{p:03d}.json")
            .get("vision_job", "")
            .startswith("vision-hi-")
        )
    ]
    # Render sequentially; PDFium itself is not thread safe.
    for p in todo:
        render_page(p)
        render_tiles(p)
    print(
        json.dumps(
            {
                "stage": "vision_started",
                "pages_remaining": len(todo),
                "workers": workers,
            }
        ),
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {executor.submit(vision_page, p, source[p]): p for p in todo}
        for job in as_completed(jobs):
            print(json.dumps(job.result(), ensure_ascii=True), flush=True)


CONFIRM_PROMPT = """Kiểm tra độc lập các đề xuất sửa OCR với ba ảnh phóng to của cùng trang sách. Không coi đề xuất là đúng.
Đọc chữ THỰC SỰ IN TRÊN ẢNH; không sửa sách bằng kiến thức y khoa. Đặc biệt không xóa một từ vốn có (ví dụ không xóa 'tủy' khỏi 'viêm xương tủy'), không đổi số liệu/phủ định hoặc tên cấu trúc vì cho rằng tác giả sai.
Đầu ra duy nhất JSON {"confirmed":[0],"rejected":[{"edit":1,"original_correct":true,"printed":"cụm đọc được trên ảnh"}],"unreadable_lines":[0]}.
confirmed chỉ chứa chỉ số edit mà before đọc sai VÀ after khớp ảnh tuyệt đối trong dòng được chỉ rõ. Không xác nhận sửa 'before==after'. Mọi edit phải nằm trong confirmed hoặc rejected, không bỏ sót. Nếu after cũng sai, rejected.original_correct=false và printed là cụm đọc chắc; nếu không chắc printed=null và thêm unreadable_lines. Không tự thay đổi dữ liệu đầu vào.
"""


def confirm_page(pn):
    proposed = read_json(OUT / f"vision/{pn:03d}.json")
    edits = proposed["edits"]
    if not edits:
        result = {
            "pdf_page": pn,
            "confirmed": [],
            "rejected": [],
            "unreadable_lines": proposed["uncertain_lines"],
            "stage": "no_edits_proposed",
        }
    else:
        data = {
            "pdf_page": pn,
            "edits": [{"edit": i, **r} for i, r in enumerate(edits)],
        }
        messages = [
            {"role": "system", "content": CONFIRM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": json.dumps(data, ensure_ascii=False)},
                    *[
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(p.read_bytes()).decode()
                            },
                        }
                        for p in render_tiles(pn)
                    ],
                ],
            },
        ]
        response = request_job(
            f"confirm-{pn:03d}", messages, max_tokens=8192, schema=CONFIRM_SCHEMA
        )
        result = response.get("value", {})
        if (
            response["status"] != "received_json"
            or not isinstance(result, dict)
            or not isinstance(result.get("confirmed"), list)
            or not isinstance(result.get("rejected"), list)
        ):
            return {"page": pn, "status": response["status"]}
        result = copy.deepcopy(result)
        ignored = [
            i
            for i in result["confirmed"]
            if not isinstance(i, int) or i not in range(len(edits))
        ]
        ignored.extend(
            r.get("edit")
            for r in result["rejected"]
            if not isinstance(r, dict) or r.get("edit") not in range(len(edits))
        )
        if ignored:
            result["discarded_out_of_scope_edit_ids"] = ignored
        result["confirmed"] = sorted(
            {
                i
                for i in result["confirmed"]
                if isinstance(i, int) and i in range(len(edits))
            }
        )
        result["rejected"] = [
            r
            for r in result["rejected"]
            if isinstance(r, dict) and r.get("edit") in range(len(edits))
        ]
        covered = set(result["confirmed"]) | {
            r.get("edit") for r in result["rejected"] if isinstance(r, dict)
        }
        manual_path = OUT / "manual-source-decisions.json"
        manually_confirmed = (
            read_json(manual_path).get("confirmed_edits", [])
            if manual_path.exists()
            else []
        )
        for i in set(range(len(edits))) - covered:
            if f"{pn}:{i}" in manually_confirmed:
                result["confirmed"].append(i)
                covered.add(i)
                result.setdefault("operator_completed_edit_ids", []).append(i)
        retained = retained_lines().get(pn, set())
        for i in set(range(len(edits))) - covered:
            if edits[i]["line"] not in retained:
                result["rejected"].append(
                    {
                        "edit": i,
                        "original_correct": False,
                        "printed": None,
                        "review_excluded": True,
                        "reason": "not_retained_book_content",
                    }
                )
                covered.add(i)
        if covered != set(range(len(edits))):
            return {"page": pn, "status": "incomplete_confirmation"}
        result.update(
            pdf_page=pn,
            stage="second_image_review",
            proposal_fingerprint=fingerprint(proposed),
        )
    write_json(OUT / f"confirmed/{pn:03d}.json", result)
    return {
        "page": pn,
        "status": result["stage"],
        "confirmed": len(result["confirmed"]),
        "rejected": len(result["rejected"]),
    }


def confirm(workers=2, limit=None):
    numbers = [
        int(p.stem)
        for p in sorted((OUT / "vision").glob("*.json"))
        if not (OUT / "confirmed" / p.name).exists()
    ]
    if limit:
        numbers = numbers[:limit]
    print(
        json.dumps({"stage": "confirmation_started", "pages": len(numbers)}), flush=True
    )
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(confirm_page, n) for n in numbers]):
            print(json.dumps(f.result(), ensure_ascii=True), flush=True)


def normalize_vision(max_page=400):
    changes = []
    for path in sorted((OUT / "vision").glob("*.json")):
        if int(path.stem) > max_page or (OUT / "confirmed" / path.name).exists():
            continue
        record = read_json(path)
        unique = []
        seen = set()
        for edit in record["edits"]:
            key = (edit["line"], edit["before"], edit["after"])
            if edit["before"] == edit["after"] or key in seen:
                continue
            seen.add(key)
            unique.append(edit)
        if unique != record["edits"]:
            changes.append(
                {
                    "pdf_page": record["pdf_page"],
                    "before_count": len(record["edits"]),
                    "after_count": len(unique),
                    "original_proposal_fingerprint": fingerprint(record),
                }
            )
            record["edits"] = unique
            record["normalization"] = "identical_edit_duplicates_removed"
            write_json(path, record)
    write_json(OUT / "audit/vision-duplicate-normalization.json", changes)
    print(json.dumps({"normalized_pages": len(changes)}), flush=True)


def coherent_confirmation(proposal, confirmation):
    """Resolve inconsistent boolean labels only using the verifier's literal read."""
    from scripts.review_2021_book import norm

    result = copy.deepcopy(confirmation)
    accepted = set(result["confirmed"])
    rejected = []
    for row in result["rejected"]:
        i = row["edit"]
        edit = proposal["edits"][i]
        printed = row.get("printed")
        if (
            isinstance(printed, str)
            and norm(printed) == norm(edit["after"])
            and norm(printed) != norm(edit["before"])
        ):
            accepted.add(i)
        elif (
            isinstance(printed, str)
            and norm(printed) == norm(edit["before"])
            and norm(printed) != norm(edit["after"])
        ):
            accepted.discard(i)
            rejected.append(
                {
                    **row,
                    "original_correct": True,
                    "verification_basis": "printed_matches_input",
                }
            )
        else:
            accepted.discard(i)
            rejected.append(row)
    result["confirmed"] = sorted(accepted)
    result["rejected"] = rejected
    return result


def retained_lines():
    result = {}
    for b in read_json(OUT / "audit/source-block-index.json"):
        pn, first, last = b["range"]
        result.setdefault(pn, set()).update(range(first, last + 1))
    manual = OUT / "manual-source-decisions.json"
    if manual.exists():
        for row in read_json(manual).get("excluded_lines", []):
            result.get(row["pdf_page"], set()).discard(row["line"])
    return result


def literal_present(needle, text):
    def normalize(value):
        value = unicodedata.normalize("NFC", value).casefold()
        value = re.sub(r"(?<=\d)(?:\^0|⁰)", "°", value)
        return re.sub(r"\s+", "", value)

    n, t = normalize(needle), normalize(text)
    if not n:
        return False
    if re.fullmatch(r"[\d.,]+", n):
        return bool(re.search(r"(?<![\d.,])" + re.escape(n) + r"(?![\d.,])", t))
    return n in t


def cosmetic_only(edit):
    """Retain input for unnecessary case, spacing, or leading list-bullet edits."""

    def key(text):
        return re.sub(r"\s+", "", unicodedata.normalize("NFC", text).casefold())

    a, b = edit["before"], edit["after"]
    return key(a) == key(b) or b == "- " + a or a == "- " + b


def blind_source_checks(workers=2, limit=None):
    from knowledge_pipeline.kg_v2.corrections import protected_markers

    pages = page_inputs()
    retained = retained_lines()
    manual = (
        read_json(OUT / "manual-source-decisions.json")
        if (OUT / "manual-source-decisions.json").exists()
        else {}
    )
    jobs = []
    for path in sorted((OUT / "confirmed").glob("*.json")):
        pn = int(path.stem)
        if (OUT / f"blind/{pn:03d}.json").exists():
            continue
        proposal = read_json(OUT / f"vision/{pn:03d}.json")
        c = coherent_confirmation(proposal, read_json(path))
        indices = []
        for i, e in enumerate(proposal["edits"]):
            if e["line"] not in retained.get(pn, set()) or f"{pn}:{i}" in manual.get(
                "confirmed_edits", []
            ) + manual.get("rejected_edits", []):
                continue
            critical = protected_markers(e["before"]) != protected_markers(
                e["after"]
            ) or len(e["before"].split()) != len(e["after"].split())
            disagree = any(
                r["edit"] == i
                and not r.get("original_correct")
                and not r.get("review_excluded")
                for r in c["rejected"]
            )
            if critical or disagree:
                indices.append(i)
        if not indices:
            write_json(
                OUT / f"blind/{pn:03d}.json",
                {"pdf_page": pn, "decisions": {}, "stage": "no_critical_edits"},
            )
            continue
        hints = {
            str(e["line"]): pages[pn]["text"].splitlines()[e["line"]]
            for i, e in enumerate(proposal["edits"])
            if i in indices
        }
        for li, text in list(hints.items()):
            for i in indices:
                e = proposal["edits"][i]
                if str(e["line"]) == li:
                    text = text.replace(e["before"], "[vùng cần đọc từ ảnh]")
            hints[li] = re.sub(r"\d+(?:[.,]\d+)*", "[số trên ảnh]", text)
        jobs.append((pn, indices, hints))
    if limit:
        jobs = jobs[:limit]

    def one(job):
        pn, indices, hints = job
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["lines"],
            "properties": {
                "lines": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(hints),
                    "properties": {
                        key: {"type": ["string", "null"], "maxLength": 4000}
                        for key in hints
                    },
                }
            },
        }
        prompt = 'Đọc độc lập ẢNH SÁCH. Chép nguyên văn đúng toàn bộ đoạn/dòng in tương ứng với các gợi ý định vị, kể cả số liệu, đơn vị, phủ định và lỗi tác giả nếu có. Các gợi ý đã che vùng nghi ngờ, KHÔNG phải văn bản để viết tiếp bằng suy đoán. Không suy kiến thức y khoa để sửa chữ. Trả JSON {"lines":{"mã dòng":"nguyên văn đoạn đọc trên ảnh"}}. Mã dòng chỉ là định danh gợi ý, không phải số dòng thị giác. Nếu không đọc chắc phần quan trọng, trả null. Không viết lời giải thích.'
        data = {"pdf_page": pn, "location_hints": hints}
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": json.dumps(data, ensure_ascii=False)},
                    *[
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(p.read_bytes()).decode()
                            },
                        }
                        for p in render_tiles(pn)
                    ],
                ],
            },
        ]
        key = f"blind-{pn:03d}-{fingerprint(data)[:8]}"
        r = request_job(key, messages, max_tokens=16384, schema=schema)
        v = r.get("value", {})
        readings = v.get("lines", {}) if isinstance(v, dict) else {}
        if r["status"] != "received_json" or set(readings) != set(hints):
            return {"page": pn, "status": r["status"]}
        proposal = read_json(OUT / f"vision/{pn:03d}.json")
        decisions = {}
        for i in indices:
            e = proposal["edits"][i]
            text = readings[str(e["line"])]
            if not isinstance(text, str):
                verdict = "unclear"
            elif literal_present(e["after"], text) and not (
                len(e["after"]) < len(e["before"])
                and literal_present(e["before"], text)
            ):
                verdict = "after"
            elif literal_present(e["before"], text):
                verdict = "before"
            else:
                verdict = "unclear"
            decisions[str(i)] = {"decision": verdict, "printed": text, "job": key}
        write_json(
            OUT / f"blind/{pn:03d}.json",
            {
                "pdf_page": pn,
                "decisions": decisions,
                "stage": "independent_image_transcription",
            },
        )
        return {
            "page": pn,
            "status": "blind_checked",
            "after": sum(d["decision"] == "after" for d in decisions.values()),
            "unclear": sum(d["decision"] == "unclear" for d in decisions.values()),
        }

    print(json.dumps({"stage": "blind_checks", "pages": len(jobs)}), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            print(json.dumps(f.result()), flush=True)


def corrected_sources():
    from scripts.review_2021_book import compose_correction, correction_char_map

    pages = page_inputs()
    patches = []
    needs = []
    manual_file = OUT / "manual-source-decisions.json"
    manual = read_json(manual_file) if manual_file.exists() else {}
    retained = retained_lines()
    for pn, page in pages.items():
        if pn < 8:
            continue
        proposal_file = OUT / f"vision/{pn:03d}.json"
        confirmation_file = OUT / f"confirmed/{pn:03d}.json"
        if not proposal_file.exists() or not confirmation_file.exists():
            needs.append({"pdf_page": pn, "reason": "image_review_not_finished"})
            continue
        proposal, confirmation = read_json(proposal_file), read_json(confirmation_file)
        confirmation = coherent_confirmation(proposal, confirmation)
        blind_path = OUT / f"blind/{pn:03d}.json"
        blind = read_json(blind_path)["decisions"] if blind_path.exists() else {}
        for index, r in blind.items():
            i = int(index)
            if r["decision"] == "after" and i not in confirmation["confirmed"]:
                confirmation["confirmed"].append(i)
            elif (
                r["decision"] in ["before", "unclear"]
                and i in confirmation["confirmed"]
            ):
                confirmation["confirmed"].remove(i)
        lines = page["text"].splitlines(keepends=True)
        starts = []
        cursor = 0
        for line in lines:
            starts.append(cursor)
            cursor += len(line)
        chosen = []
        for i, edit in enumerate(proposal["edits"]):
            if edit["line"] not in retained.get(pn, set()):
                continue
            if cosmetic_only(edit):
                continue
            if i not in confirmation["confirmed"] and f"{pn}:{i}" not in manual.get(
                "confirmed_edits", []
            ):
                continue
            if f"{pn}:{i}" in manual.get("rejected_edits", []):
                continue
            # Protect amounts, comparisons and negation for a dedicated human check.
            from knowledge_pipeline.kg_v2.corrections import protected_markers

            if (
                protected_markers(edit["before"]) != protected_markers(edit["after"])
                and f"{pn}:{i}" not in manual.get("confirmed_edits", [])
                and blind.get(str(i), {}).get("decision") != "after"
            ):
                needs.append(
                    {
                        **edit,
                        "pdf_page": pn,
                        "edit": i,
                        "reason": "numeric_or_negation_change_requires_visual_check",
                    }
                )
                continue
            if (
                len(edit["before"].split()) != len(edit["after"].split())
                and f"{pn}:{i}" not in manual.get("confirmed_edits", [])
                and blind.get(str(i), {}).get("decision") != "after"
            ):
                needs.append(
                    {
                        **edit,
                        "pdf_page": pn,
                        "edit": i,
                        "reason": "word_insertion_or_deletion_requires_visual_check",
                    }
                )
                continue
            if edit["before"] == edit["after"]:
                continue
            for found in re.finditer(re.escape(edit["before"]), lines[edit["line"]]):
                for op, a, b, c, d in difflib.SequenceMatcher(
                    None, edit["before"], edit["after"], autojunk=False
                ).get_opcodes():
                    if op == "equal":
                        continue
                    chosen.append(
                        (
                            starts[edit["line"]] + found.start() + a,
                            starts[edit["line"]] + found.start() + b,
                            edit["after"][c:d],
                            i,
                        )
                    )
        for index, edit in enumerate(manual.get("overrides", [])):
            if edit["pdf_page"] != pn:
                continue
            if edit["before"] not in lines[edit["line"]]:
                raise ValueError("manual_override_not_in_input_line")
            for found in re.finditer(re.escape(edit["before"]), lines[edit["line"]]):
                for op, a, b, c, d in difflib.SequenceMatcher(
                    None, edit["before"], edit["after"], autojunk=False
                ).get_opcodes():
                    if op != "equal":
                        chosen.append(
                            (
                                starts[edit["line"]] + found.start() + a,
                                starts[edit["line"]] + found.start() + b,
                                edit["after"][c:d],
                                -index - 1,
                            )
                        )
        unique = {}
        for start, end, after, i in chosen:
            key = (start, end)
            if key in unique and unique[key][0] != after:
                needs.append(
                    {
                        "pdf_page": pn,
                        "reason": "conflicting_confirmed_edits",
                        "range": list(key),
                    }
                )
            else:
                unique[key] = (after, i)
        ordered = sorted([(a, b, v[0], v[1]) for (a, b), v in unique.items()])
        accepted = []
        for start, end, after, i in ordered:
            if accepted and start < accepted[-1][1]:
                needs.append(
                    {"pdf_page": pn, "reason": "overlapping_confirmed_edits", "edit": i}
                )
                continue
            accepted.append((start, end, after, i))
        mapping = correction_char_map(page)
        for start, end, after, i in reversed(accepted):
            # An insertion inherits the raw span of its adjacent source character.
            touched = mapping[start:end] or mapping[max(0, start - 1) : start + 1]
            raw_start = min(r[0] for r in touched)
            raw_end = max(r[1] for r in touched)
            patch_id = "COMP2021_" + fingerprint([pn, start, end, after])[:24]
            lineage = tuple(sorted({patch_id} | {k for r in touched for k in r[2]}))
            before = page["text"][start:end]
            mapping[start:end] = [(raw_start, raw_end, lineage)] * len(after)
            page["text"] = page["text"][:start] + after + page["text"][end:]
            patches.append(
                {
                    "id": patch_id,
                    "pdf_page": pn,
                    "before": before,
                    "after": after,
                    "input_start": start,
                    "input_end": end,
                    "raw_start": raw_start,
                    "raw_end": raw_end,
                    "proposal_edit": i,
                    "verification": "operator_visual"
                    if i < 0 or f"{pn}:{i}" in manual.get("confirmed_edits", [])
                    else "three_image_checks"
                    if str(i) in blind
                    else "two_image_checks",
                    "expert_verified": False,
                }
            )
        compose_correction(page, mapping)
        for rejected in confirmation["rejected"]:
            if rejected.get("review_excluded"):
                continue
            if proposal["edits"][rejected["edit"]]["line"] not in retained.get(
                pn, set()
            ):
                continue
            if cosmetic_only(proposal["edits"][rejected["edit"]]):
                continue
            if isinstance(rejected, dict) and rejected.get("original_correct") is False:
                key = f"{pn}:{rejected['edit']}"
                if key not in manual.get("confirmed_edits", []) + manual.get(
                    "rejected_edits", []
                ) + manual.get("rejected_proposals_resolved", []) and blind.get(
                    str(rejected["edit"]), {}
                ).get("decision") not in ["after", "before"]:
                    needs.append(
                        {
                            "pdf_page": pn,
                            "reason": "checks_disagree_on_printed_text",
                            "rejected": rejected,
                            "proposal": proposal["edits"][rejected["edit"]],
                        }
                    )
        grounded_uncertain = {
            proposal["edits"][r["edit"]]["line"]
            for r in confirmation["rejected"]
            if isinstance(r, dict)
            and not r.get("review_excluded")
            and r.get("printed") is None
            and r.get("original_correct") is False
            and f"{pn}:{r['edit']}"
            not in manual.get("confirmed_edits", [])
            + manual.get("rejected_edits", [])
            + manual.get("rejected_proposals_resolved", [])
            and blind.get(str(r["edit"]), {}).get("decision") not in ["after", "before"]
        }
        for li in set(confirmation.get("unreadable_lines", [])) & grounded_uncertain:
            if f"{pn}:{li}" not in manual.get("readable_lines", []):
                needs.append(
                    {"pdf_page": pn, "line": li, "reason": "image_line_uncertain"}
                )
        for index, r in blind.items():
            if proposal["edits"][int(index)]["line"] not in retained.get(pn, set()):
                continue
            if cosmetic_only(proposal["edits"][int(index)]):
                continue
            if r["decision"] == "unclear" and f"{pn}:{index}" not in manual.get(
                "confirmed_edits", []
            ) + manual.get("rejected_edits", []) + manual.get(
                "rejected_proposals_resolved", []
            ):
                needs.append(
                    {
                        "pdf_page": pn,
                        "edit": int(index),
                        "reason": "independent_readings_disagree",
                        "proposal": proposal["edits"][int(index)],
                        "blind_printed": r["printed"],
                    }
                )
    jsonl(OUT / "audit/corrected-pages.jsonl", [pages[k] for k in sorted(pages)])
    write_json(OUT / "audit/completion-ocr-patches.json", patches)
    write_json(OUT / "audit/source-attention.json", needs)
    print(
        json.dumps(
            {
                "stage": "corrected_sources",
                "patches": len(patches),
                "attention_items": len(needs),
                "attention_pages": len({r["pdf_page"] for r in needs}),
            }
        ),
        flush=True,
    )


def corrected_pages():
    return {
        p["pdf_page"]: p
        for p in map(
            json.loads,
            (OUT / "audit/corrected-pages.jsonl")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
    }


def chapter_sources(number, pages):
    plan = read_json(OUT / "audit/plan.json")
    chapter = next(c for c in plan["chapters"] if c["lesson_number"] == number)
    retained = retained_lines()
    return chapter, [
        {
            "page": pn,
            "lines": [
                (i, line)
                for i, line in enumerate(pages[pn]["text"].splitlines())
                if i in retained.get(pn, set())
            ],
        }
        for pn in range(chapter["pdf_pages"]["start"], chapter["pdf_pages"]["end"] + 1)
        if pn in pages
    ]


def node_input(item, imported):
    n = item["graph"] or (item["raw"][0]["candidate"] if item["raw"] else {})
    return {
        "key": item["key"],
        "type": n.get("type"),
        "name": n.get("name", n.get("text")),
        "kind": n.get("kind"),
        "ranges": item["ranges"],
        "already_imported": n.get("id") in imported,
        "is_chapter_root": item.get("is_chapter_root", False),
        "raw_basis": [
            r["candidate"].get("basis")
            for r in item["raw"]
            if r["candidate"].get("basis")
        ],
    }


def decision_schema(kind, keys):
    from knowledge_pipeline.kg_v2.contracts import RELATIONS, TYPES

    nullable = {"type": ["string", "null"], "maxLength": 300}
    ranges = {
        "type": "array",
        "maxItems": 40,
        "items": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "integer", "minimum": 0},
        },
    }
    fields = {
        "key": {"type": "string", "enum": keys},
        "action": {
            "type": "string",
            "enum": ["keep", "correct", "merge", "reject"]
            if kind == "nodes"
            else ["keep", "correct", "reject"],
        },
        "type": {
            "type": ["string", "null"],
            "enum": list(TYPES if kind == "nodes" else RELATIONS) + [None],
        },
        "ranges": ranges,
        "reason": {"type": "string", "minLength": 1, "maxLength": 300},
    }
    if kind == "nodes":
        fields.update(
            name=nullable,
            merge_into=nullable,
            parent=nullable,
            kind={"enum": ["cognitive", "practical", None]},
        )
    else:
        fields.update(
            from_key=nullable,
            to_key=nullable,
            condition={"type": ["string", "null"], "maxLength": 1200},
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [kind],
        "properties": {
            kind: {
                "type": "array",
                "minItems": len(keys),
                "maxItems": len(keys),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(fields),
                    "properties": fields,
                },
            }
        },
    }


def node_reviews(chapters=None, workers=2):
    proposals = read_json(OUT / "audit/proposals.json")
    pages = corrected_pages()
    imported = {n["id"] for n in read_json(PREVIOUS / "combined/graph.json")["nodes"]}
    jobs = []
    for number in chapters or range(1, 37):
        chapter, source = chapter_sources(number, pages)
        rows = [
            node_input(r, imported)
            for r in proposals["nodes"]
            if r["chapter"] == number
        ]
        priority = {
            r["key"]: i
            for i, r in enumerate(
                sorted(rows, key=lambda r: (not r["already_imported"], r["key"]))
            )
        }
        for r in rows:
            r["canonical_priority"] = priority[r["key"]]
        # Full chapter context remains available while limiting output size.
        for first in range(0, len(rows), 60):
            group = rows[first : first + 60]
            payload = {
                "chapter": chapter,
                "source": source,
                "nodes": group,
                "group_index": first // 60,
                "chapter_node_index": [
                    {
                        k: n[k]
                        for k in [
                            "key",
                            "type",
                            "name",
                            "already_imported",
                            "canonical_priority",
                        ]
                    }
                    for n in rows
                ],
            }
            key = f"nodes-v2-{number:02d}-{first // 60:02d}-{fingerprint(payload)[:10]}"
            write_json(OUT / f"review-inputs/{key}.json", payload)
            jobs.append((key, payload))

    def one(job):
        key, payload = job
        expected = {n["key"] for n in payload["nodes"]}
        r = request_job(
            key,
            [
                {"role": "system", "content": NODE_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=16384,
            schema=decision_schema("nodes", sorted(expected)),
        )
        value = r.get("value", {})
        rows = value.get("nodes", []) if isinstance(value, dict) else []
        actual = [d.get("key") for d in rows if isinstance(d, dict)]
        okay = (
            r["status"] == "received_json"
            and set(actual) == expected
            and len(actual) == len(expected)
        )
        if r["status"] == "received_json":
            unique = []
            unresolved = []
            for identifier in expected:
                matches = [
                    d
                    for d in rows
                    if isinstance(d, dict) and d.get("key") == identifier
                ]
                if matches and len({fingerprint(d) for d in matches}) == 1:
                    unique.append(matches[0])
                else:
                    unresolved.append(identifier)
            write_json(
                OUT / f"node-reviews/{key}.json",
                {
                    "chapter": payload["chapter"]["lesson_number"],
                    "decisions": unique,
                    "job": key,
                    "omitted_or_conflicting": sorted(unresolved),
                },
            )
            write_json(
                OUT
                / f"node-reviews/active-{payload['chapter']['lesson_number']:02d}-{payload['group_index']:02d}.json",
                {"path": f"{key}.json"},
            )
        return {
            "job": key,
            "status": "node_decisions_received" if okay else r["status"],
            "complete_keys": okay,
            "http_status": r["http_status"],
            "seconds": r["latency_seconds"],
        }

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            print(json.dumps(f.result()), flush=True)


def line_refs(ranges, pages, locators):
    result = []
    for pn, first, last in ranges:
        if (
            pn not in pages
            or not isinstance(first, int)
            or not isinstance(last, int)
            or first < 0
            or last < first
        ):
            raise ValueError("invalid_source_line_range")
        page = pages[pn]
        lines = page["text"].splitlines(keepends=True)
        if last >= len(lines):
            raise ValueError("source_range_outside_page")
        start = sum(map(len, lines[:first]))
        end = sum(map(len, lines[: last + 1]))
        while end > start and page["text"][end - 1] in "\r\n":
            end -= 1
        text = page["text"][start:end]
        if not text.strip():
            raise ValueError("empty_source_quote")
        identifier = (
            "LOCCOMP_"
            + fingerprint(
                [page["source_id"], pn, start, end, page["correction"]["revision"]]
            )[:24]
        )
        if identifier not in locators:
            locators[identifier] = {
                "locator_id": identifier,
                "source_id": page["source_id"],
                "document_edition_id": page["document_edition_id"],
                "source_sha256": read_json(OUT / "audit/plan.json")["source_sha256"],
                "ocr_sha256": page["ocr_sha256"],
                "pdf_page": pn,
                "char_start": start,
                "char_end": end,
                "text": text,
                "corrected_char_start": start,
                "corrected_char_end": end,
                **trace_raw(page["correction"], start, end),
            }
        result.append(
            {
                "source_id": page["source_id"],
                "locator_id": identifier,
                "pdf_pages": [pn],
                "printed_pages": [],
                "excerpt": text,
            }
        )
    return result


def retained_ranges(ranges, retained):
    result = []
    for pn, first, last in ranges:
        for li in range(first, last + 1):
            if li not in retained.get(pn, set()):
                continue
            if result and result[-1][0] == pn and result[-1][2] == li - 1:
                result[-1][2] = li
            else:
                result.append([pn, li, li])
    return result


def phrase_present(needle, text):
    from scripts.review_2021_book import norm

    # An explicitly printed abbreviation may interrupt a full name, e.g.
    # "Gãy trên lồi cầu (TLC) xương cánh tay". Do not strip medical qualifiers,
    # quantities or arbitrary parenthetical prose.
    direct = bool(norm(needle)) and (" " + norm(needle) + " ") in (
        " " + norm(text) + " "
    )
    text = re.sub(r"\([A-ZĐ][A-ZĐ .–/-]{0,14}\)", " ", text)
    return (
        direct
        or bool(norm(needle))
        and (" " + norm(needle) + " ") in (" " + norm(text) + " ")
    )


def entity_type_issue(kind, name):
    """Reject explicit actors unsupported by the closed medical ontology."""
    organism = r"^(?:tụ cầu|liên cầu|trực khuẩn|vi khuẩn|Staph\.|Strep\.|Clostridium|C\.\s*tetani|Cl\.|Staphylococcus|Streptococcus|Mycobacterium|M\.\s*(?:ulcerans|marinum)|Enterobacter|Enterococcus|Eikenella|Pasteurella|Pseudomonas|Escherichia|E\.\s*coli|Klebsiella|Acinetobacter)\b"
    toxin = r"^(?:Alpha|Beta|Delta|Epsilon|Iota|Kappa|Lamda|Lambda|Mucin|Muy|Nuy|Phi)\s+toxin\b|^Độc tố\b"
    if kind in [
        "Condition",
        "Finding",
        "Drug",
        "Intervention",
        "Anatomy",
    ] and re.search(organism + "|" + toxin, name, re.IGNORECASE):
        return "unsupported_microorganism_or_toxin_entity_type"
    if kind in ["Condition", "Finding", "Drug", "Intervention", "Anatomy"] and re.match(
        r"^Tai nạn\b", name, re.IGNORECASE
    ):
        return "accident_event_is_not_supported_medical_entity_type"
    if kind == "Drug" and re.match(
        r"^(chỉ|chì|đinh|kim|vít|nẹp|khung|xi măng)\b|^Thuốc hoặc vật liệu\b",
        name,
        re.IGNORECASE,
    ):
        return "hardware_or_material_is_not_a_standalone_drug"
    if kind == "ClinicalPrinciple" and re.match(
        r"^(Cơ chế|Chấn thương|Lực\s|Hệ thống giữ vững|Liền xương|Quá trình liền xương|Sinh lý liền xương|Cơ sinh học|Sấp\s|Giai đoạn ủ bệnh|Lý thuyết|Dịch tễ học)",
        name,
        re.IGNORECASE,
    ):
        return "mechanism_physiology_or_background_is_not_normative_clinical_principle"
    if kind == "Intervention" and re.match(
        r"^(?:Đinh|Kim|Chỉ|Chì|Khung)\b|^Vít(?:$|\s+xương cứng\b)|^Nẹp\s+(?:khóa|móc|mốc|vít)\b",
        name,
        re.IGNORECASE,
    ):
        return "bare_hardware_is_not_a_procedure"
    return None


def reviewed_nodes():
    from knowledge_pipeline.kg_v2.contracts import TYPES
    from scripts.review_2021_book import norm

    proposals = read_json(OUT / "audit/proposals.json")
    pages = corrected_pages()
    plan = {
        c["lesson_number"]: c for c in read_json(OUT / "audit/plan.json")["chapters"]
    }
    learning = [
        b
        for b in read_json(OUT / "audit/source-block-index.json")
        if b["role"] in ["learning_objective", "practice_requirement", "procedure"]
    ]
    decisions = {}
    faults = []
    locators = {}
    for path in sorted((OUT / "node-reviews").glob("active-*.json")):
        for d in read_json(OUT / "node-reviews" / read_json(path)["path"])["decisions"]:
            decisions[d["key"]] = d
    for path in sorted((OUT / "node-repairs").glob("active-*.json")):
        identifier = path.stem[len("active-") :]
        for d in read_json(OUT / "node-repairs" / read_json(path)["path"])["decisions"]:
            if d["key"] == identifier:
                decisions[identifier] = d
    operator_file = OUT / "operator-node-decisions.json"
    if operator_file.exists():
        for d in read_json(operator_file)["decisions"]:
            decisions[d["key"]] = d
    valid = {}
    rejected = []
    merged = {}
    lookup = {n["key"]: n for n in proposals["nodes"]}
    retained = retained_lines()
    heading_lines, body_lines = set(), set()
    for block in read_json(OUT / "audit/source-block-index.json"):
        pn, first, last = block["range"]
        target = (
            heading_lines
            if block["kind"] in ["heading", "system_heading"]
            else body_lines
        )
        target.update((pn, i) for i in range(first, last + 1))
    for key, item in lookup.items():
        d = decisions.get(key)
        if d is None:
            faults.append(
                {
                    "key": key,
                    "reason": "missing_node_decision",
                    "chapter": item["chapter"],
                }
            )
            continue
        if not isinstance(d.get("reason"), str) or not d["reason"].strip():
            faults.append(
                {
                    "key": key,
                    "reason": "missing_decision_reason",
                    "chapter": item["chapter"],
                }
            )
            continue
        if d.get("action") == "reject":
            rejected.append({"key": key, "reason": d.get("reason"), "decision": d})
            continue
        if d.get("action") == "merge":
            target = d.get("merge_into")
            if (
                target not in lookup
                or target == key
                or lookup[target]["chapter"] != item["chapter"]
            ):
                d = copy.deepcopy(d)
                d.update(action="correct", merge_into=None)
                d["reason"] = (
                    "Invalid merge refused; require independent source verification. "
                    + d["reason"]
                )
                decisions[key] = d
            target_decision = decisions.get(target, {})
            # A hierarchy subtype is not an equivalent identity. Do not collapse
            # different names solely because the model proposes a merge.
            if d["action"] == "merge" and (
                norm(d.get("name") or "") != norm(target_decision.get("name") or "")
                or d.get("type") != target_decision.get("type")
                or d.get("type") == "ClassificationCategory"
                and (
                    not d.get("parent")
                    or d.get("parent") != target_decision.get("parent")
                )
            ):
                d = copy.deepcopy(d)
                d["action"] = "correct"
                d["merge_into"] = None
                d["reason"] = (
                    "Merge refused: distinct source identities; retain the independently sourced entity. "
                    + d["reason"]
                )
                decisions[key] = d
            elif d["action"] == "merge":
                merged[key] = target
                d = copy.deepcopy(d)
                d["action"] = "correct"
        try:
            if d.get("action") not in ["keep", "correct"] or d.get("type") not in TYPES:
                raise ValueError("invalid_node_decision")
            ranges = d.get("ranges")
            if not isinstance(ranges, list) or not ranges:
                raise ValueError("no_description_source_ranges")
            filtered = retained_ranges(ranges, retained)
            if filtered != ranges:
                d = copy.deepcopy(d)
                d["excluded_noncontent_lines_removed"] = True
                d["ranges"] = filtered
                decisions[key] = d
                ranges = filtered
            if not ranges:
                raise ValueError("no_retained_medical_source_in_citation")
            chapter = plan[item["chapter"]]
            if any(
                not chapter["pdf_pages"]["start"] <= r[0] <= chapter["pdf_pages"]["end"]
                for r in ranges
            ):
                raise ValueError("node_description_outside_chapter")
            refs = line_refs(ranges, pages, locators)
            text = "\n".join(s["excerpt"] for s in refs)
            selected_lines = {
                (pn, i) for pn, first, last in ranges for i in range(first, last + 1)
            }
            if (
                not key.startswith("B")
                and d["type"] not in ["Skill", "SampleQuestion"]
                and selected_lines <= heading_lines - body_lines
                and not re.search(r":\s*\S.{12,}", text)
            ):
                raise ValueError("description_is_only_heading_without_medical_content")
            name = d.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("empty_node_identity")
            type_issue = entity_type_issue(d["type"], name)
            if type_issue:
                raise ValueError(type_issue)
            if d["type"] in ["Condition", "Finding", "Drug"] and re.search(
                r"^(Clostridium|C\.\s*tetani|Cl\.|Staphylococcus|Streptococcus|M\.\s*(ulcerans|marinum)|Enterobacter|Enterococcus)",
                name,
                re.IGNORECASE,
            ):
                raise ValueError("microorganism_outside_supported_entity_types")
            if d["type"] == "Drug" and re.match(
                r"^(chỉ|đinh|kim|vít|nẹp|khung)\b", name, re.IGNORECASE
            ):
                raise ValueError("hardware_cannot_be_drug")
            if not phrase_present(name, text) and d["type"] not in [
                "Skill",
                "SampleQuestion",
            ]:
                plain = re.sub(r"\s*\([^()]*\)", "", name).strip()
                classification = re.sub(
                    r"^Phân (loại|độ)\s+", "", name, flags=re.IGNORECASE
                )
                stage = (
                    re.search(
                        r"(Giai đoạn\s+\d+\s*[-–:.]?\s*"
                        + re.escape(
                            re.sub(r"^Giai đoạn\s+", "", name, flags=re.IGNORECASE)
                        )
                        + r")",
                        text,
                        re.IGNORECASE,
                    )
                    if name.lower().startswith("giai đoạn ")
                    else None
                )
                if plain != name and phrase_present(plain, text):
                    name = plain
                elif (
                    d["type"] == "Classification"
                    and classification != name
                    and phrase_present(classification, text)
                    and re.search(r"phân (loại|độ|chia)", text, re.IGNORECASE)
                ):
                    name = classification
                elif stage:
                    name = stage.group(1)
                else:
                    raise ValueError("reviewed_identity_not_in_selected_source")
            n = {
                "id": item["graph"]["id"]
                if item["graph"]
                else "COMP2021_" + fingerprint(key)[:28],
                "type": d["type"],
                "name": name,
                "aliases": [],
                "content": [{"text": text, "sources": refs}],
            }
            if n["type"] == "SampleQuestion":
                qblocks = [
                    b
                    for b in read_json(OUT / "audit/source-block-index.json")
                    if b["role"] == "question"
                ]
                if not any(
                    any(
                        r[0] == b["range"][0]
                        and r[1] <= b["range"][2]
                        and b["range"][1] <= r[2]
                        for r in ranges
                    )
                    for b in qblocks
                ):
                    raise ValueError("question_outside_actual_question_section")
                if not re.search(r"\bCâu\s*\d+", text, re.IGNORECASE):
                    raise ValueError("question_has_no_actual_question_label")
                n = {
                    "id": n["id"],
                    "type": "SampleQuestion",
                    "text": text,
                    "format": "open_ended",
                    "options": [],
                    "answer": None,
                    "explanation": None,
                    "sources": refs,
                    "answer_sources": [],
                }
            elif n["type"] == "Skill":
                n.pop("aliases")
                n["kind"] = d.get("kind")
                if n["kind"] not in ["cognitive", "practical"]:
                    raise ValueError("missing_skill_kind")
                if not any(
                    any(
                        r[0] == b["range"][0]
                        and r[1] <= b["range"][2]
                        and b["range"][1] <= r[2]
                        for r in ranges
                    )
                    for b in learning
                ):
                    raise ValueError("skill_without_objective_or_procedure_basis")
            valid[key] = n
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            faults.append(
                {
                    "key": key,
                    "reason": str(exc)
                    if isinstance(exc, ValueError)
                    else type(exc).__name__,
                    "decision": d,
                    "chapter": item["chapter"],
                }
            )
    resolved = {}
    for key, initial_target in merged.items():
        if key not in valid:
            continue
        seen = {key}
        target = initial_target
        while target in merged and target not in seen:
            seen.add(target)
            target = merged[target]
        if target in seen or target not in valid:
            decisions[key] = copy.deepcopy(decisions[key])
            decisions[key].update(
                action="correct",
                merge_into=None,
                merge_refused_reason="unapproved_or_cyclic_target_independent_source_retained",
            )
        else:
            resolved[key] = target
    for key, n in list(valid.items()):
        if n["type"] != "ClassificationCategory":
            continue
        parent = decisions[key].get("parent")
        parent = resolved.get(parent, parent)
        if parent not in valid and isinstance(parent, str):
            matches = [
                k
                for k, v in valid.items()
                if v["type"] == "Classification"
                and lookup[k]["chapter"] == lookup[key]["chapter"]
                and norm(v["name"]) == norm(parent)
            ]
            if len(matches) == 1:
                parent = matches[0]
                decisions[key]["parent"] = parent
        if parent not in valid or valid[parent]["type"] != "Classification":
            faults.append(
                {
                    "key": key,
                    "reason": "category_parent_not_approved_classification",
                    "chapter": lookup[key]["chapter"],
                    "decision": decisions[key],
                }
            )
            valid.pop(key)
    for key, target in list(resolved.items()):
        if key not in valid or target not in valid:
            resolved.pop(key)
            if key in valid:
                decisions[key] = copy.deepcopy(decisions[key])
                decisions[key].update(
                    action="correct",
                    merge_into=None,
                    merge_refused_reason="canonical_target_failed_parent_validation",
                )
    contributions = {k: valid.pop(k) for k in resolved}
    write_json(
        OUT / "audit/node-resolution.json",
        {
            "nodes": valid,
            "merge_map": resolved,
            "rejected": rejected,
            "faults": faults,
            "locators": list(locators.values()),
            "decisions": decisions,
            "merge_contributions": contributions,
        },
    )
    print(
        json.dumps(
            {
                "stage": "node_resolution",
                "accepted": len(valid),
                "merged": len(resolved),
                "rejected": len(rejected),
                "faults": len(faults),
            }
        ),
        flush=True,
    )
    return valid, resolved, rejected, faults, locators


def repair_nodes(
    chapters=None,
    workers=2,
    review_revision="v3_verbatim_identity_parent_keys_only",
    fault_reasons=None,
):
    proposals = read_json(OUT / "audit/proposals.json")
    lookup = {n["key"]: n for n in proposals["nodes"]}
    nodes, _, _, faults, _ = reviewed_nodes()
    pages = corrected_pages()
    selected = set(chapters or range(1, 37))
    jobs = []
    for number in sorted(selected):
        errors = [
            f
            for f in faults
            if f.get("chapter") == number
            and (not fault_reasons or f["reason"] in fault_reasons)
        ]
        if not errors:
            continue
        chapter, source = chapter_sources(number, pages)
        for first in range(0, len(errors), 12):
            group = errors[first : first + 12]
            keys = [f["key"] for f in group]
            payload = {
                "chapter": chapter,
                "source": source,
                "validation_errors": group,
                "review_revision": review_revision,
                "nodes": [
                    node_input(
                        lookup[k],
                        {
                            n["id"]
                            for n in read_json(PREVIOUS / "combined/graph.json")[
                                "nodes"
                            ]
                        },
                    )
                    for k in keys
                ],
                "approved_targets": [
                    {"key": k, "type": n["type"], "name": n.get("name", n.get("text"))}
                    for k, n in nodes.items()
                    if lookup[k]["chapter"] == number
                ],
            }
            key = f"node-fix-v3-{number:02d}-{fingerprint(payload)[:12]}"
            write_json(OUT / f"review-inputs/{key}.json", payload)
            jobs.append((key, payload, keys))

    def one(job):
        key, payload, keys = job
        prompt = (
            NODE_PROMPT
            + "\nFor description_is_only_heading_without_medical_content, cite the actual explanatory paragraph or list under that heading, including its conditions. A title, table caption or image label alone is insufficient. Reject if no descriptive source exists; do not invent a definition."
            + "\nĐây là sửa các quyết định không qua kiểm tra nguồn/cấu trúc. Chỉ quyết định cho nodes trong yêu cầu. Tên phải là chuỗi THỰC SỰ có trong ranges, không diễn giải tên mới. Không merge subtype vào supertype. Nếu không có mô tả và định danh đủ căn cứ, reject với lý do cụ thể, không cố ép taxonomy. Với merge, chỉ dùng approved_targets tương đương thật. parent chỉ là KEY của Classification trong approved_targets, không trả tên tự do. Không suy thực hành từ lý thuyết."
        )
        response = request_job(
            key,
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=6500,
            schema=decision_schema("nodes", keys),
        )
        value = response.get("value", {})
        rows = value.get("nodes", []) if isinstance(value, dict) else []
        counts = {
            k: sum(d.get("key") == k for d in rows if isinstance(d, dict)) for k in keys
        }
        usable = [
            d for d in rows if isinstance(d, dict) and counts.get(d.get("key")) == 1
        ]
        if usable:
            write_json(
                OUT / f"node-repairs/{key}.json", {"decisions": usable, "job": key}
            )
            for d in usable:
                write_json(
                    OUT / f"node-repairs/active-{d['key']}.json",
                    {"path": f"{key}.json"},
                )
        return {
            "job": key,
            "status": response["status"],
            "decisions": len(usable),
            "expected": len(keys),
        }

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            print(json.dumps(f.result()), flush=True)
    reviewed_nodes()


def edge_reviews(chapters=None, workers=2):
    nodes, merge, _rejected, faults, _ = reviewed_nodes()
    node_decisions = read_json(OUT / "audit/node-resolution.json")["decisions"]
    proposals = read_json(OUT / "audit/proposals.json")
    pages = corrected_pages()
    lookup = {n["key"]: n for n in proposals["nodes"]}
    selected = set(chapters or range(1, 37))
    groups = {}
    automatic = []
    faultkeys = {r["key"] for r in faults}
    for e in proposals["edges"]:
        if e.get("chapter") is None:
            automatic.append(
                {
                    "key": e["key"],
                    "action": "reject",
                    "reason": "missing_or_incompatible_chapter_scope_in_extraction_endpoints",
                }
            )
            continue
        if e.get("chapter") not in selected:
            continue
        left, right = (
            merge.get(e["from_key"], e["from_key"]),
            merge.get(e["to_key"], e["to_key"]),
        )
        if left not in nodes or right not in nodes:
            if e["from_key"] not in faultkeys and e["to_key"] not in faultkeys:
                automatic.append(
                    {
                        "key": e["key"],
                        "action": "reject",
                        "reason": "endpoint_rejected_or_missing_from_source_grounded_nodes",
                    }
                )
            continue
        raw = e["graph"] or e["raw"][0]["candidate"]
        signature = fingerprint(
            [
                e["chapter"],
                left,
                right,
                raw.get("type"),
                raw.get("condition"),
                sorted(e["ranges"]),
            ]
        )
        group = groups.setdefault(
            signature,
            {
                "key": e["key"],
                "original_keys": [],
                "chapter": e["chapter"],
                "from_key": left,
                "to_key": right,
                "type": raw.get("type"),
                "condition": raw.get("condition"),
                "ranges": e["ranges"],
            },
        )
        group["original_keys"].append(e["key"])
    write_json(OUT / "audit/edge-review-groups.json", list(groups.values()))
    write_json(OUT / "audit/automatic-edge-rejections.json", automatic)
    jobs = []
    for number in sorted(selected):
        chapter, source = chapter_sources(number, pages)
        rows = [e for e in groups.values() if e["chapter"] == number]
        index = [
            {"key": k, "type": n["type"], "name": n.get("name", n.get("text"))}
            for k, n in nodes.items()
            if lookup[k]["chapter"] == number
        ]
        for row in index:
            if row["type"] == "ClassificationCategory":
                parent = node_decisions[row["key"]].get("parent")
                parent = merge.get(parent, parent)
                row["parent_key"] = parent
                row["parent_name"] = nodes.get(parent, {}).get("name")
        for first in range(0, len(rows), 25):
            payload = {
                "chapter": chapter,
                "source": source,
                "nodes": index,
                "edges": rows[first : first + 25],
            }
            key = f"edges-{number:02d}-{first // 25:02d}-{fingerprint(payload)[:10]}"
            write_json(OUT / f"review-inputs/{key}.json", payload)
            jobs.append((key, payload))

    def one(job):
        key, payload = job
        keys = [e["key"] for e in payload["edges"]]
        response = request_job(
            key,
            [
                {"role": "system", "content": EDGE_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=6500,
            schema=decision_schema("edges", keys),
        )
        value = response.get("value", {})
        rows = value.get("edges", []) if isinstance(value, dict) else []
        counts = {
            k: sum(d.get("key") == k for d in rows if isinstance(d, dict)) for k in keys
        }
        usable = [
            d for d in rows if isinstance(d, dict) and counts.get(d.get("key")) == 1
        ]
        if usable:
            write_json(
                OUT / f"edge-reviews/{key}.json", {"decisions": usable, "job": key}
            )
            for d in usable:
                write_json(
                    OUT / f"edge-reviews/active-{d['key']}.json",
                    {"path": f"{key}.json"},
                )
        return {
            "job": key,
            "status": response["status"],
            "decisions": len(usable),
            "expected": len(keys),
        }

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            print(json.dumps(f.result()), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--vision", action="store_true")
    p.add_argument("--repair-vision", action="store_true")
    p.add_argument("--inventory", action="store_true")
    p.add_argument("--reextract-missing", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--build-sources", action="store_true")
    p.add_argument("--normalize-vision", action="store_true")
    p.add_argument("--blind-check", action="store_true")
    p.add_argument("--review-nodes", action="store_true")
    p.add_argument("--resolve-nodes", action="store_true")
    p.add_argument("--repair-nodes", action="store_true")
    p.add_argument("--review-edges", action="store_true")
    p.add_argument("--chapters", type=int, nargs="+")
    p.add_argument("--pages", type=int, nargs="+")
    p.add_argument("--workers", type=int, choices=[1, 2], default=2)
    p.add_argument("--limit", type=int)
    p.add_argument("--review-revision", default="v3_verbatim_identity_parent_keys_only")
    p.add_argument("--fault-reasons", nargs="+")
    a = p.parse_args()
    if a.prepare:
        prepare()
    if a.vision:
        vision(a.pages, a.workers)
    if a.repair_vision:
        repair_vision(a.workers, a.limit)
    if a.inventory:
        source_inventory()
    if a.reextract_missing:
        reextract_missing(a.workers)
    if a.normalize_vision:
        normalize_vision()
    if a.confirm:
        confirm(a.workers, a.limit)
    if a.build_sources:
        corrected_sources()
    if a.blind_check:
        blind_source_checks(a.workers, a.limit)
    if a.review_nodes:
        node_reviews(a.chapters, a.workers)
    if a.resolve_nodes:
        reviewed_nodes()
    if a.repair_nodes:
        repair_nodes(a.chapters, a.workers, a.review_revision, a.fault_reasons)
    if a.review_edges:
        edge_reviews(a.chapters, a.workers)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- no credential-bearing tracebacks
        detail = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch(r"[A-Za-z_]+", str(exc))
            else None
        )
        print(
            json.dumps(
                {"status": "failed", "error_type": type(exc).__name__, "reason": detail}
            )
        )
        raise SystemExit(1) from None
