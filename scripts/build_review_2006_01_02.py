"""Rebuild the explicit PDF comparison for lessons 1-2; never calls LLM/DB.

Decisions below were made after reading rendered PDF pages 8-15, not inferred
by the builder. Raw extraction, OCR and the active draft registry are read-only.
"""

import copy
import hashlib
import html
import json
from collections import Counter
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.corrections import protected_markers, trace_raw
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import validate_locators

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/knowledge-extraction/v2/source-review-20261102"
PARENT = ROOT / "data/knowledge-extraction/v2/book-2006-full-wait/shards"
SID = "SRC_ORTHO_EMERGENCY_001"
PDF_HASH = "d95f9d803e46c1bb8b41a2b35fc53add5dd8959df1b3107a83f8e0c324469007"

# Only changes visible in the PDF. No conversion to modern spelling, units,
# treatment recommendations, or inferred numeric denominators.
CHANGES = {
    8: {
        5: [("lớp mô dưới da", "lớp mỡ dưới da"), ("cần cơ", "cân cơ")],
        6: [("phăng", "phẳng"), ("khâu dính", "khâu đính")],
        7: [("qua cần", "qua cân")],
        8: [("tốc độ chứng", "tốc độ chừng")],
        9: [
            ("rách rộng", "rạch rộng"),
            ("rách dọc", "rạch dọc"),
            ("cần", "cân"),
            ("Thi 2", "Thì 2"),
            ("khâu dính", "khâu đính"),
        ],
        11: [("da cần", "da cân"), ("song tùy", "song tuỷ")],
        12: [("da, cần", "da, cân")],
        13: [("khâu dính", "khâu đính")],
        15: [("Vật", "Vạt"), ("vật", "vạt"), ("lộ trợ", "lộ trơ")],
    },
    9: {
        0: [("thương bị hoại tử", "thường bị hoại tử"), ("lớp cần", "lớp cân")],
        1: [("đập nát", "dập nát"), ("mất da có mỡ", "mất da có mủ")],
        8: [("vết cần", "vết cắn")],
        10: [("máy quần", "máy quấn"), ("mất hay bị xé", "mặt hay bị xếch")],
        13: [("lột gân", "lột găng"), ("khâu dính", "khâu đính")],
        14: [("bưng", "bụng"), ("đứt bàn tay giẩu", "đút bàn tay giấu")],
    },
    10: {
        0: [("chịu lực tốt", "chịu lực tỳ")],
        3: [("trở da như mất võng, tái", "trổ da như mắt võng, tãi")],
        4: [("đỡ hồng", "đỏ hồng"), ("vẫn hồng", "vẫn hỏng")],
        5: [("Cây da", "Cấy da")],
        6: [("mẫu da", "mẩu da")],
        9: [("Vật", "Vạt"), ("vật", "vạt")],
        10: [("Vật", "Vạt")],
        12: [("éch", "ếch"), ("bằng sinh vật", "băng sinh vật")],
    },
    11: {
        0: [("áp lực càng", "áp lực căng")],
        1: [("máu tụ đã bị", "máu tụ đỡ bị"), ("làm người", "làm nguội")],
        2: [("rẽ móng", "rễ móng")],
    },
    12: {
        2: [
            ("Loại gãy phổ biến là gãy cẳng tay", "Loại gãy phổ biến là gãy cành tươi"),
            ("hay gãy rối loạn", "hay gây rối loạn"),
            ("đi chứng", "di chứng"),
        ],
        7: [
            ("vũng", "vững"),
            ("chơi xương", "chồi xương"),
            ("cần trở", "cản trở"),
            ("mổ găm bó", "mổ gặm bỏ"),
            ("xương chổi", "xương chồi"),
        ],
        9: [
            ("lối cầu", "lồi cầu"),
            ("bị gãy khúc", "bị gấp khúc"),
            ("bị kệt", "bị kẹt"),
        ],
        10: [("lối cầu", "lồi cầu")],
    },
    13: {
        0: [("cần trở", "cản trở"), ("cẳng tay vào trong", "cẳng tay vẹo vào trong")],
        1: [
            ("lỗi cầu", "lồi cầu"),
            ("chổng tay", "chống tay"),
            ("còn đính cơ", "còn dính cơ"),
            ("cơ kéo đi", "cơ co đi"),
        ],
        2: [("lỗi cầu", "lồi cầu")],
        5: [("Chỉ bất động", "Chi bất động"), ("mạnh gãy", "mảnh gãy")],
        6: [("mạnh gãy", "mảnh gãy")],
        8: [("không dễ cặp", "không đề cập")],
        9: [("Chòm", "Chỏm"), ("ghim đính", "ghim đinh")],
        10: [
            ("mòm", "mỏm"),
            ("chỉ đính", "chỉ định"),
            ("ghim đính", "ghim đinh"),
            ("nắn ép", "néo ép"),
        ],
        11: [("gãy góc", "gấp góc"), ("chòm", "chỏm")],
    },
    14: {
        0: [
            ("nán", "nắn"),
            ("khuỷu dễ", "khuỷu để"),
            ("xoay sắp", "xoay sấp"),
            ("chòm", "chỏm"),
            ("xoay ngược", "xoay ngửa"),
        ],
        1: [("thác mắc", "thắc mắc")],
        2: [("loại gây", "loại gãy")],
        3: [
            ("xương dài", "xương đùi"),
            ("Có gãy", "Có gặp"),
            ("Chòm", "Chỏm"),
            ("chòm", "chỏm"),
            ("đỉnh can", "dính can"),
            ("tập tành", "tập tễnh"),
            ("Thấy thuốc", "Thầy thuốc"),
            ("đảm chỉ định", "dám chỉ định"),
            ("cao gãy đôi", "cao gấp đôi"),
        ],
        4: [
            ("xương dài", "xương đùi"),
            ("Gãy khá", "Gặp khá"),
            ("Gãy từ trẻ", "Gặp từ trẻ"),
            ("xương gót", "xương gối"),
            ("chợp lại", "chụp lại"),
        ],
        5: [
            ("xương dài", "xương đùi"),
            ("chống liền", "chóng liền"),
            ("thấy thuốc", "thầy thuốc"),
            ("lệch gót", "lệch gối"),
            ("bị gãy góc", "bị gấp góc"),
        ],
        7: [("xương gót", "xương gối"), ("hay gãy góc", "hay gấp góc")],
        10: [
            ("vùng gót", "vùng gối"),
            ("lôi cầu dài", "lồi cầu đùi"),
            ("ít gãy", "ít gặp"),
        ],
        12: [("hiếm gãy", "hiếm gặp")],
    },
    15: {
        0: [("SỰ PHÁT TRIỂN", "SỤN PHÁT TRIỂN")],
        1: [("sự phát triển", "sụn phát triển")],
        2: [("sự phát triển", "sụn phát triển")],
        3: [("sự phát triển", "sụn phát triển")],
        4: [("sự phát triển", "sụn phát triển")],
        5: [("lối cầu", "lồi cầu"), ("sửa trực", "sửa trục")],
        6: [("sự phát triển", "sụn phát triển")],
    },
}


def jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in values),
        encoding="utf-8",
    )


class Review:
    def __init__(self, lesson, first_page, last_page, title):
        self.lesson, self.title = lesson, title
        self.folder = OUT / f"chapters/2006-bai-{lesson:02d}"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.parents = sorted(PARENT.glob(f"bai-{lesson:02d}*"))
        self.nodes, self.edges, self.local, self.raw, self.held = {}, {}, {}, {}, {}
        self.pages, self.patches, self.locs = {}, [], {}
        self.decisions, self.mapping, self.pending, self.missing = [], {}, [], []
        self.edge_hold_reasons = {}
        self.node_ranges = {}
        registry = read_json(ROOT / "knowledge_pipeline/kg_v2/canonical-registry.json")
        bindings_used = []
        for parent in self.parents:
            g = read_json(parent / "graph.json")
            self.nodes.update({n["id"]: copy.deepcopy(n) for n in g["nodes"]})
            self.edges.update({e["id"]: copy.deepcopy(e) for e in g["edges"]})
            ids = read_json(parent / "audit/draft_id_mapping.json")
            for item in read_json(parent / "audit/identity_registry.json"):
                candidate = item["candidate_id"]
                if candidate in ids:
                    target = registry["bindings"].get(candidate, ids[candidate])
                    if target != ids[candidate]:
                        raise ValueError(
                            "canonical_binding_requires_explicit_existing_identity_review"
                        )
                    self.local[item["window_id"], item["local_id"]] = target
                    if candidate in registry["bindings"]:
                        bindings_used.append(candidate)
            for raw_file in (parent / "audit/raw").glob("*.json"):
                raw = read_json(raw_file)
                for kind in ["nodes", "edges"]:
                    for r in raw.get(kind, []):
                        self.raw[raw_file.stem, kind[:-1], r["local_id"]] = r
            for filename in ["review_items.json", "rejected.json"]:
                for item in read_json(parent / "audit" / filename):
                    if item.get("kind") in {"node", "edge"} and item.get("candidate"):
                        self.held[item["window_id"], item["kind"], item["local_id"]] = (
                            item
                        )
            for row in map(
                json.loads,
                (parent / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines(),
            ):
                if first_page <= row["pdf_page"] <= last_page:
                    self.pages[row["pdf_page"]] = copy.deepcopy(row)
        assert set(self.pages) == set(range(first_page, last_page + 1))
        self.original_nodes, self.original_edges = (
            copy.deepcopy(self.nodes),
            copy.deepcopy(self.edges),
        )
        # Explicit specs below follow each planned shard in order, then the
        # shard's persisted graph order (not a new global ID sort).
        self.original_nodes_order = list(self.nodes)
        self.registry_check = {
            "canonical_bindings_checked": True,
            "existing_bindings_reused": bindings_used,
            "global_registry_modified": False,
            "new_cross_book_equivalence_confirmed": False,
            "note": "No confirmed source-anchored binding for these candidates. Similar names in open-fracture registry and shoulder graph have different clinical scope; no name-only merge.",
        }
        for page, row in self.pages.items():
            raw = row["raw_text"]
            corrected = ""
            segments = []
            rpos = 0
            image_path = OUT / f"audit/2006-pdf-{page}.png"
            image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            for line_no, line in enumerate(raw.splitlines(keepends=True)):
                before = line.rstrip("\r\n")
                ending = line[len(before) :]
                after = before
                for old, new in CHANGES.get(page, {}).get(line_no, []):
                    assert old in after, (page, line_no, old)
                    after = after.replace(old, new)
                patch_id = None
                if after != before:
                    patch_id = f"SOURCE_REVIEW_2006_{page}_{line_no:02d}"
                    markers_changed = protected_markers(before) != protected_markers(
                        after
                    )
                    assert not markers_changed, (
                        page,
                        line_no,
                        "protected_marker_changed",
                    )
                    self.patches.append(
                        {
                            "id": patch_id,
                            "source_id": SID,
                            "pdf_page": page,
                            "raw_start": rpos,
                            "raw_end": rpos + len(before),
                            "before": before,
                            "after": after,
                            "ocr_sha256": row["ocr_sha256"],
                            "source_pdf_sha256": PDF_HASH,
                            "image_path": image_path.relative_to(ROOT).as_posix(),
                            "image_sha256": image_hash,
                            "decision": "confirmed_visual_transcription",
                            "expert_verified": False,
                            "numeric_or_negation_markers_changed": markers_changed,
                        }
                    )
                segments.append(
                    {
                        "raw_start": rpos,
                        "raw_end": rpos + len(before),
                        "corrected_start": len(corrected),
                        "corrected_end": len(corrected) + len(after),
                        "patch_id": patch_id,
                    }
                )
                corrected += after
                if ending:
                    segments.append(
                        {
                            "raw_start": rpos + len(before),
                            "raw_end": rpos + len(line),
                            "corrected_start": len(corrected),
                            "corrected_end": len(corrected) + len(ending),
                            "patch_id": None,
                        }
                    )
                    corrected += ending
                rpos += len(line)
            row["text"] = corrected
            row["correction"] = {
                "raw_text": raw,
                "corrected_text": corrected,
                "segments": segments,
                "patch_ids": [p["id"] for p in self.patches if p["pdf_page"] == page],
                "revision": fingerprint([raw, corrected, segments]),
                "expert_review": "unverified",
            }

    def nid(self, index):
        return self.original_nodes_order[index]

    def source(self, page, start_line, end_line=None):
        row = self.pages[page]
        lines = row["text"].splitlines(keepends=True)
        end_line = start_line + 1 if end_line is None else end_line
        start = sum(map(len, lines[:start_line]))
        end = sum(map(len, lines[:end_line]))
        text = row["text"][start:end].rstrip("\r\n")
        end = start + len(text)
        lid = (
            "LOCR_"
            + fingerprint([SID, page, start, end, row["correction"]["revision"]])[:24]
        )
        self.locs[lid] = {
            "locator_id": lid,
            "source_id": SID,
            "document_edition_id": row["document_edition_id"],
            "source_sha256": PDF_HASH,
            "ocr_sha256": row["ocr_sha256"],
            "pdf_page": page,
            "char_start": start,
            "char_end": end,
            "corrected_char_start": start,
            "corrected_char_end": end,
            "text": text,
            **trace_raw(row["correction"], start, end),
        }
        return {
            "source_id": SID,
            "locator_id": lid,
            "pdf_pages": [page],
            "printed_pages": [str(page - 1)],
            "excerpt": text,
        }

    def content(self, ranges):
        sources = [self.source(*r) for r in ranges]
        return [{"text": "\n".join(s["excerpt"] for s in sources), "sources": sources}]

    def node(
        self,
        index,
        ranges,
        name=None,
        kind=None,
        reason="Restore full source context, conditions and continuation; visually compare PDF, retain exact numeric/negation markers.",
    ):
        identifier = self.nid(index)
        n = self.nodes[identifier]
        before = copy.deepcopy(n)
        n["content"] = self.content(ranges)
        n["aliases"] = []
        if name:
            n["name"] = name
        if kind:
            n["type"] = kind
        self.node_ranges[identifier] = ranges
        self.decisions.append(
            {
                "kind": "node",
                "id": identifier,
                "decision": "correct",
                "before": before,
                "after": copy.deepcopy(n),
                "reason": reason,
                "pdf_actually_viewed": sorted({r[0] for r in ranges}),
            }
        )

    def merge(self, source, target, reason):
        src, dst = self.nid(source), self.nid(target)
        self.mapping[src] = dst
        self.decisions.append(
            {
                "kind": "node",
                "id": src,
                "decision": "merge",
                "before": self.original_nodes[src],
                "after": copy.deepcopy(self.nodes[dst]),
                "kept_id": dst,
                "reason": reason,
                "pdf_actually_viewed": sorted(self.pages),
            }
        )
        del self.nodes[src]

    def hold_node(self, index, ranges, reason):
        identifier = self.nid(index)
        item = {
            "kind": "node",
            "id": identifier,
            "decision": "hold",
            "before": self.original_nodes[identifier],
            "after": None,
            "reason": reason,
            "compared_sources": [self.source(*r) for r in ranges],
        }
        self.pending.append(item)
        self.decisions.append(item)
        del self.nodes[identifier]

    def recover(self, window, local, ranges, name, kind, target=None):
        key = window, "node", local
        item = self.held[key]
        identifier = (
            target
            or "DRN_"
            + uuid5(
                NAMESPACE_URL, f"medresident:source-review:2006:{window}:{local}"
            ).hex
        )
        self.local[window, local] = identifier
        if target is None:
            self.nodes[identifier] = {
                "id": identifier,
                "name": name,
                "type": kind,
                "aliases": [],
                "content": self.content(ranges),
            }
            self.node_ranges[identifier] = ranges
        self.decisions.append(
            {
                "kind": "node",
                "window_id": window,
                "local_id": local,
                "decision": "merge_recovered" if target else "recover",
                "before": item["candidate"],
                "after": copy.deepcopy(self.nodes[identifier]),
                "id": identifier,
                "reason": "Exact source object identified in this chapter; complete its empty/misquoted content from the displayed PDF. No name-only cross-source merge.",
                "pdf_actually_viewed": sorted({r[0] for r in ranges}),
            }
        )
        return identifier

    def edge(self, left, right, relation, ranges, condition=None, identifier=None):
        identifier = (
            identifier
            or "DRE_"
            + fingerprint(
                ["source-review-2006", self.lesson, left, relation, right, condition]
            )[:24]
        )
        row = {
            "id": identifier,
            "from_id": left,
            "to_id": right,
            "type": relation,
            "condition": condition,
            "sources": [self.source(*r) for r in ranges],
        }
        assert left != right
        return row

    def finish(self, retained_edges, recovered_edges):
        # Each existing edge and each distinct held candidate gets an explicit
        # disposition. Technical duplicate review messages remain in parent audit.
        edges = {}
        for identifier, before in self.original_edges.items():
            spec = retained_edges.get(identifier)
            if spec:
                left = self.mapping.get(before["from_id"], before["from_id"])
                right = self.mapping.get(before["to_id"], before["to_id"])
                after = self.edge(
                    left, right, before["type"], spec[0], spec[1], identifier
                )
                edges[identifier] = after
                self.decisions.append(
                    {
                        "kind": "edge",
                        "id": identifier,
                        "decision": "correct",
                        "before": before,
                        "after": after,
                        "reason": "Include the paragraph proving this relationship and preserve its clinical scope/conditions.",
                        "pdf_actually_viewed": sorted({r[0] for r in spec[0]}),
                    }
                )
            else:
                item = {
                    "kind": "edge",
                    "id": identifier,
                    "decision": "hold",
                    "before": before,
                    "after": None,
                    "reason": self.edge_hold_reasons[identifier],
                    "pdf_actually_viewed": sorted(self.pages),
                }
                self.pending.append(item)
                self.decisions.append(item)
        decided_nodes = {
            (d.get("window_id"), d.get("local_id"))
            for d in self.decisions
            if d["kind"] == "node"
        }
        for (window, kind, local), item in self.held.items():
            if kind == "node":
                if (window, local) in decided_nodes:
                    continue
                decision = {
                    "kind": kind,
                    "window_id": window,
                    "local_id": local,
                    "decision": "hold",
                    "before": item["candidate"],
                    "after": None,
                    "reason": "Source heading groups a surgical flap with traumatic avulsion; not a homogeneous Classification/HAS_CATEGORY model. Requires a schema-compatible modelling decision.",
                    "compared_sources": [self.source(8, 14, 16), self.source(9, 0, 2)],
                }
            else:
                spec = recovered_edges.get((window, local))
                after = self.edge(*spec) if spec else None
                if after:
                    signature = (
                        after["from_id"],
                        after["to_id"],
                        after["type"],
                        after["condition"],
                    )
                    same = next(
                        (
                            e
                            for e in edges.values()
                            if (e["from_id"], e["to_id"], e["type"], e["condition"])
                            == signature
                        ),
                        None,
                    )
                    if same:
                        after = same
                    else:
                        edges[after["id"]] = after
                decision = {
                    "kind": kind,
                    "window_id": window,
                    "local_id": local,
                    "decision": "recover" if after else "hold",
                    "before": item["candidate"],
                    "after": after,
                    "reason": "Manually resolved endpoints/direction from PDF, after recovering source-backed nodes."
                    if after
                    else "Existing schema does not express the proposed part-of/material/category-treatment relation, or mixed classification. Do not coerce node types just to pass validation.",
                    "pdf_actually_viewed": sorted(self.pages),
                }
            self.decisions.append(decision)
            if decision["decision"] == "hold":
                self.pending.append(decision)
        graph = {
            "schema_version": "medical-kg-v2",
            "nodes": sorted(self.nodes.values(), key=lambda r: r["id"]),
            "edges": sorted(edges.values(), key=lambda r: r["id"]),
        }
        dry_run_loader(graph)
        prior_manifest = self.folder / "review-manifest.json"
        if (
            prior_manifest.exists()
            and any(self.folder.glob("import-*/import-manifest.json"))
            and read_json(prior_manifest)["graph_fingerprint"] != fingerprint(graph)
        ):
            raise ValueError(
                "imported_overlay_is_immutable_create_a_new_review_revision"
            )
        write_json(self.folder / "graph.json", graph)
        jsonl(self.folder / "reviewed-nodes.jsonl", graph["nodes"])
        jsonl(self.folder / "reviewed-edges.jsonl", graph["edges"])
        jsonl(self.folder / "audit/pages.jsonl", self.pages.values())
        write_json(self.folder / "audit/locators.json", list(self.locs.values()))
        write_json(self.folder / "ocr-patches.json", self.patches)
        write_json(self.folder / "decisions.json", self.decisions)
        write_json(
            self.folder / "id-mapping.json",
            {
                "draft_remap": self.mapping,
                "local_to_stable": [
                    {"window_id": w, "local_id": l, "id": self.mapping.get(i, i)}
                    for (w, l), i in sorted(self.local.items())
                ],
                "canonical_registry_check": self.registry_check,
            },
        )
        write_json(self.folder / "pending-review.json", self.pending)
        write_json(
            self.folder / "rejected.json",
            [
                {
                    "reason": r["reason"],
                    "original_proposal": r["before"],
                    "disposition": "retained_outside_graph_not_discarded",
                }
                for r in self.pending
            ],
        )
        write_json(self.folder / "need-extraction.json", self.missing)
        checked = validate_locators(graph, self.folder)
        decisions = Counter(d["decision"] for d in self.decisions)
        manifest = {
            "book_year": 2006,
            "lesson_number": self.lesson,
            "title": self.title,
            "review_status": "source_compared_records_separated",
            "graph_fingerprint": fingerprint(graph),
            "nodes_before": len(self.original_nodes),
            "edges_before": len(self.original_edges),
            "nodes_after": len(graph["nodes"]),
            "edges_after": len(graph["edges"]),
            "decisions": dict(decisions),
            "pending_records": len(self.pending),
            "missing_content_items": len(self.missing),
            "ocr_patch_count": len(self.patches),
            "pdf_actually_viewed": sorted(self.pages),
            "quote_and_raw_trace_checked_locators": checked,
            "expert_verified": False,
            "new_llm_calls": 0,
            "parents": [p.relative_to(ROOT).as_posix() for p in self.parents],
            "complete_book_review": False,
        }
        write_json(self.folder / "review-manifest.json", manifest)
        report = [
            f"# 2006 — Bài {self.lesson}: {self.title}",
            "",
            "Đã đọc toàn bộ node/cạnh và đề xuất bị giữ ngoài của bài; đã xem trực tiếp ảnh PDF "
            + ", ".join(map(str, sorted(self.pages)))
            + ".",
            "Đây là đối chiếu nguồn, chưa phải chuyên gia y khoa duyệt. Các bản ghi độc lập đã kiểm tra được tách khỏi phần chưa rõ.",
            "",
            "## Cần xem tiếp",
            "",
            *[
                f"- {r['before'].get('name', r['before'].get('local_id', r['before'].get('id', '')))}: {r['reason']}"
                for r in self.pending
            ],
            "",
            "## Thiếu hoặc còn khó đọc",
            "",
            *[f"- {m['reason']} — PDF {m['pdf_pages']}" for m in self.missing],
            "",
            "## Kết quả",
            "",
            f"Node {len(self.original_nodes)} → {len(graph['nodes'])}; cạnh {len(self.original_edges)} → {len(graph['edges'])}. OCR patches: {len(self.patches)}.",
            "Các số liệu, phủ định và nội dung lịch sử của sách được giữ; không dùng kiến thức ngoài để cập nhật sách.",
            "",
            "## Nội dung sau đối chiếu",
            "",
        ]
        names = {n["id"]: n["name"] for n in graph["nodes"]}
        for n in graph["nodes"]:
            report += [f"### {n['name']} ({n['type']})", ""]
            for c in n["content"]:
                report += [
                    c["text"],
                    "",
                    "Nguồn: "
                    + "; ".join(
                        "PDF "
                        + str(s["pdf_pages"][0])
                        + " / trang in "
                        + ",".join(s["printed_pages"])
                        for s in c["sources"]
                    ),
                    "",
                ]
            for e in graph["edges"]:
                if e["from_id"] == n["id"]:
                    report += [
                        f"- {e['type']} → {names[e['to_id']]}"
                        + (f"; điều kiện: {e['condition']}" if e["condition"] else "")
                    ]
            report.append("")
        (self.folder / "review.md").write_text("\n".join(report), encoding="utf-8")
        cards = [
            '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đối chiếu bài '
            + str(self.lesson)
            + "</title><style>body{font:16px system-ui;max-width:1050px;margin:32px auto;padding:0 16px}pre{white-space:pre-wrap}summary{cursor:pointer}small{color:#555}article{border-top:1px solid #ccc;padding:12px 0}</style>",
            f"<h1>Bài {self.lesson}: {html.escape(self.title)}</h1>",
            "<p>Đã xem PDF; kiểm quote/raw trace bằng code. Chưa phải chuyên gia y khoa duyệt. Hash, ID và log nằm trong audit.</p>",
            "<h2>Cần quyết định / còn thiếu</h2><pre>"
            + html.escape("\n".join(report[6 : report.index("## Kết quả")]))
            + "</pre>",
            "<h2>Nội dung</h2>",
        ]
        for n in graph["nodes"]:
            cards += [
                "<article><h3>"
                + html.escape(n["name"])
                + " <small>"
                + n["type"]
                + "</small></h3>"
            ]
            for c in n["content"]:
                cards += [
                    "<pre>"
                    + html.escape(c["text"])
                    + "</pre><small>Nguồn: "
                    + ", ".join(
                        '<a href="../../audit/2006-pdf-'
                        + str(s["pdf_pages"][0])
                        + '.png">PDF '
                        + str(s["pdf_pages"][0])
                        + "</a>"
                        for s in c["sources"]
                    )
                    + "</small>"
                ]
            for e in graph["edges"]:
                if e["from_id"] == n["id"]:
                    cards += [
                        "<p>"
                        + e["type"]
                        + " → "
                        + html.escape(names[e["to_id"]])
                        + "; "
                        + html.escape(e["condition"] or "")
                        + "</p>",
                        "<details><summary>Nguồn quan hệ: PDF "
                        + ", ".join(str(s["pdf_pages"][0]) for s in e["sources"])
                        + "</summary><pre>"
                        + html.escape("\n".join(s["excerpt"] for s in e["sources"]))
                        + "</pre></details>",
                    ]
            cards += ["</article>"]
        (self.folder / "review.html").write_text(
            "\n".join(cards) + "</html>", encoding="utf-8"
        )
        print(json.dumps(manifest, ensure_ascii=True))


def lesson1():
    r = Review(1, 8, 11, "Vết thương phần mềm")
    specs = {
        0: ([(8, 11, 14)], None),
        1: ([(9, 0, 2)], "Bong lóc da do tai nạn"),
        2: ([(9, 0, 2)], "Băng ướt nước muối cho vết thương mất da có mủ"),
        3: ([(9, 2, 9)], "Khâu kín vết thương đầu mặt hoặc bàn tay sau cắt lọc"),
        4: ([(8, 5, 7)], "Cắt lọc vết thương rách da đơn thuần"),
        6: ([(8, 7, 11)], None),
        7: ([(8, 1, 4)], None),
        8: ([(9, 2, 9)], None),
        9: ([(8, 1, 5)], None),
        10: ([(8, 0, 1), (9, 2, 9)], None),
        11: ([(8, 14, 16)], "Vạt da có cuống"),
        12: ([(8, 5, 7)], None),
        13: ([(9, 12, 15)], None),
        14: ([(9, 9, 11)], "Xử trí lột da đầu"),
        15: ([(9, 12, 14)], "Xử trí lột da bàn tay như lột găng"),
        16: ([(9, 9, 10), (9, 11, 12)], "Xử trí lột da đầu kèm mất màng xương"),
        17: ([(9, 15, 17)], "Vá da biểu bì tại nơi cho vạt che gót chân"),
        18: ([(9, 12, 15)], None),
        19: ([(10, 0, 1)], None),
        20: ([(9, 15, 17)], "Chuyển vạt da gan chân trong che gót chân"),
        21: ([(9, 12, 13), (9, 14, 15)], None),
        22: ([(9, 9, 12)], None),
        23: ([(9, 15, 17)], None),
        24: ([(9, 12, 14)], "Lột da bàn tay như lột găng"),
        25: ([(11, 0, 2)], None),
        27: ([(10, 1, 2), (10, 3, 5)], None),
        28: ([(10, 14, 15), (11, 0, 1)], None),
        29: ([(11, 0, 1)], None),
        30: ([(10, 11, 13)], "Vá da khác loại"),
        31: ([(11, 3, 4)], "Ghim đinh Kirschner khi gãy đốt 3 di lệch nhiều"),
        32: ([(10, 11, 13)], "Vá da đồng loại"),
        33: ([(10, 9, 11)], None),
        34: ([(10, 5, 7)], None),
        35: ([(11, 4, 5)], "Vá miếng da 1/2 dày khi mất móng"),
        36: ([(11, 2, 3)], "Khâu rễ móng"),
        37: ([(11, 3, 4)], "Gãy xương đốt 3 kèm thương tổn giường móng"),
        38: ([(10, 7, 9)], None),
        39: ([(10, 13, 15)], None),
        40: ([(11, 2, 3)], "Bong rễ móng"),
        41: ([(11, 4, 5)], None),
        42: ([(10, 7, 8)], None),
        43: ([(11, 5, 8)], "Tổ chức hạt phát triển lên góc móng"),
        44: ([(11, 5, 8)], None),
        45: ([(11, 5, 8)], None),
    }
    for i, (ranges, name) in specs.items():
        r.node(i, ranges, name, kind="Intervention" if i == 11 else None)
    r.merge(
        5,
        1,
        "The same traumatic degloving paragraph PDF9 defines both candidates; remove the incorrect category representation. Surgical flap remains a separate Intervention.",
    )
    r.hold_node(
        26,
        [(10, 1, 3)],
        "Da tự thân is donor material in this immunity paragraph; Anatomy vs graft procedure is not established. Keep proposal and source outside graph.",
    )
    w1 = "WINDOW2_58c2ab62574ee0cc1cbced84"
    w3 = "WINDOW2_423fb086fb0c3f52b7e18924"
    w4 = "WINDOW2_845d6b09347e757e9211154d"
    w5 = "WINDOW2_35bde679bec716fcf247e5d1"
    r.recover(
        w1,
        "VET_THUONG_PHAN_MEM",
        [(9, 2, 9)],
        "Vết thương phần mềm",
        "Condition",
        r.nid(10),
    )
    cls = r.recover(
        w1,
        "LOAI_VET_THUONG_PHAN_MEM",
        [(8, 1, 14)],
        "Phân loại vết thương phần mềm theo mức tổn thương (2006)",
        "Classification",
    )
    deep = r.recover(
        w1,
        "VET_THUONG_SAU_VAO_CO",
        [(8, 7, 14)],
        "Vết thương sâu qua cân đến lớp cơ",
        "ClassificationCategory",
    )
    face = r.recover(
        w3,
        "node_vet_thuong_dau_mat",
        [(9, 2, 9)],
        "Vết thương phần mềm đầu mặt",
        "Condition",
    )
    hand = r.recover(
        w3,
        "node_vet_thuong_ban_tay",
        [(9, 2, 9)],
        "Vết thương phần mềm bàn tay",
        "Condition",
    )
    hc = r.recover(
        w4,
        "node_phan_loai_lot_da",
        [(9, 12, 15)],
        "Phân loại lột da bàn tay theo kiểu lột (2006)",
        "Classification",
    )
    r.recover(w5, "R_MONG", [(10, 13, 15)], "Rễ móng", "Anatomy")
    r.recover(w5, "MONG", [(10, 13, 15)], "Móng", "Anatomy")
    retained = {}
    for e in r.original_edges.values():
        left, right = e["from_id"], e["to_id"]
        cond = e["condition"]
        if left == r.nid(10) and right == r.nid(3):
            r.edge_hold_reasons[e["id"]] = (
                "Generic closure edge omits anatomical and bite exceptions. Recovered face/hand edges carry the complete conditions instead."
            )
            continue
        if left == r.nid(23) and right == r.nid(17):
            r.edge_hold_reasons[e["id"]] = (
                "The epidermal graft covers the donor site after moving the plantar flap, not the heel defect itself. Do not infer a direct heel→epidermal-graft management relation."
            )
            continue
        if left == r.nid(1):
            ranges = [(9, 0, 2)]
            cond = "Vết thương mất da có mủ; nồng độ muối theo tình trạng nền/tổ chức hạt được mô tả trong nguồn"
        elif left == r.nid(10):
            ranges = [(9, 2, 9)]
            cond = (
                "Hầu hết sau cắt lọc; ngoại lệ đầu mặt và bàn tay; vết cắn luôn để hở"
            )
        elif left == r.nid(22):
            ranges = [(9, 9, 12)]
        elif left == r.nid(23):
            ranges = [(9, 15, 17)]
        elif left == r.nid(39):
            ranges = [(10, 13, 15), (11, 0, 1)]
        elif left == r.nid(41):
            ranges = [(11, 4, 5)]
        elif left == r.nid(37):
            ranges = [(11, 3, 4)]
            cond = "Nếu gãy xương di lệch nhiều"
        elif left == r.nid(40):
            ranges = [(11, 2, 3)]
        elif left == r.nid(45):
            ranges = [(11, 5, 8)]
        else:
            raise ValueError(("unreviewed_existing_edge", e["id"]))
        retained[e["id"]] = (ranges, cond)
    recovered = {
        (w1, "E1"): (r.nid(10), cls, "CLASSIFIED_BY", [(8, 0, 14)]),
        (w1, "E2"): (cls, r.nid(7), "HAS_CATEGORY", [(8, 1, 4)]),
        (w1, "E3"): (cls, r.nid(9), "HAS_CATEGORY", [(8, 1, 5)]),
        (w1, "E4"): (cls, r.nid(12), "HAS_CATEGORY", [(8, 1, 2), (8, 5, 7)]),
        (w1, "E5"): (cls, deep, "HAS_CATEGORY", [(8, 1, 2), (8, 7, 14)]),
        (w1, "E6"): (r.nid(6), deep, "IS_A", [(8, 7, 11)]),
        (w1, "E7"): (r.nid(0), deep, "IS_A", [(8, 7, 8), (8, 11, 14)]),
        (w3, "edge_1"): (face, r.nid(10), "IS_A", [(9, 2, 9)]),
        (w3, "edge_2"): (hand, r.nid(10), "IS_A", [(9, 2, 9)]),
        (w3, "edge_5"): (
            face,
            r.nid(3),
            "MANAGED_BY",
            [(9, 2, 9)],
            "Sau cắt lọc; nếu sâu đặt dẫn lưu; vết cắn luôn để hở",
        ),
        (w3, "edge_6"): (
            hand,
            r.nid(3),
            "MANAGED_BY",
            [(9, 2, 9)],
            "Sau cắt lọc; nếu sâu đặt dẫn lưu; vết cắn luôn để hở",
        ),
        (w4, "edge_1"): (r.nid(18), hc, "CLASSIFIED_BY", [(9, 12, 15)]),
        (w4, "edge_2"): (hc, r.nid(24), "HAS_CATEGORY", [(9, 12, 14)]),
        (w4, "edge_3"): (hc, r.nid(21), "HAS_CATEGORY", [(9, 12, 13), (9, 14, 15)]),
    }
    r.missing = [
        {
            "kind": "source_content_held_for_modelling",
            "pdf_pages": [10],
            "reason": "Đoạn da tự thân/miễn dịch PDF10 dòng2 còn ngoài graph do type chưa rõ; không mất bản gốc.",
            "sources": [r.source(10, 1, 3)],
        },
        {
            "kind": "invalid_relation_candidates_retained",
            "pdf_pages": [8, 9, 10, 11],
            "reason": "Các quan hệ part-of, vật liệu, Category→Intervention chưa biểu diễn được bằng schema hiện tại; content nguồn vẫn giữ trong node hợp lệ.",
        },
    ]
    r.finish(retained, recovered)


def lesson2():
    r = Review(2, 12, 15, "Gãy xương ở trẻ em")
    specs = {
        0: ([(12, 0, 1), (13, 10, 11)], "Gãy mỏm khuỷu ở trẻ em"),
        1: ([(12, 0, 1), (14, 10, 11)], "Gãy vùng gối ở trẻ em"),
        2: ([(12, 0, 1), (12, 6, 7)], "Gãy xương đòn ở trẻ sơ sinh"),
        3: ([(15, 0, 1), (15, 6, 9)], "Gãy bong sụn phát triển đầu dưới xương đùi"),
        4: (
            [(12, 0, 1), (12, 9, 10), (13, 0, 1)],
            "Gãy trên lồi cầu xương cánh tay ở trẻ em",
        ),
        5: ([(12, 0, 1), (14, 4, 6), (14, 7, 10)], "Gãy thân xương đùi ở trẻ em"),
        7: ([(12, 0, 1), (12, 7, 9)], "Gãy cổ xương cánh tay ở trẻ em"),
        8: ([(12, 0, 5)], None),
        9: (
            [(15, 0, 1), (15, 5, 6)],
            "Đục xương sửa trục sau gãy thấp trên lồi cầu xương cánh tay ở trẻ em",
        ),
        10: ([(13, 7, 9)], "Trật khớp khuỷu ở trẻ em"),
        11: ([(12, 0, 3)], "Gãy cành tươi ở trẻ em"),
        12: ([(12, 0, 3)], "Mổ sửa trục xương sau gãy gần đầu xương ở trẻ em"),
        13: ([(12, 0, 1), (13, 9, 10)], "Gãy cổ xương quay ở trẻ em"),
        14: ([(15, 0, 4)], "Nắn xương gãy vùng sụn phát triển ở trẻ em"),
        15: ([(15, 0, 1), (15, 5, 6)], "Gãy thấp trên lồi cầu xương cánh tay ở trẻ em"),
        16: (
            [(12, 0, 1), (13, 1, 3), (13, 4, 7)],
            "Gãy lồi cầu ngoài xương cánh tay ở trẻ em",
        ),
        17: ([(12, 0, 1), (14, 3, 4)], "Gãy cổ xương đùi ở thiếu niên"),
        18: ([(13, 11, 12), (14, 0, 2)], "Gãy Monteggia ở trẻ em"),
    }
    for i, (ranges, name) in specs.items():
        r.node(i, ranges, name)
    r.merge(
        6,
        8,
        "Same chapter condition, one record contains heading only. The retained record has the full general paragraph. Source identity, not name similarity.",
    )
    w1 = "WINDOW2_d309b7784375d853563551eb"
    w2 = "WINDOW2_664c1c3798e00cb366b34156"
    physis = r.recover(
        w2,
        "node_gãy_vùng_sự_phát_triển",
        [(15, 0, 4)],
        "Gãy vùng sụn phát triển ở trẻ em",
        "Condition",
    )
    retained = {}
    for e in r.original_edges.values():
        left = e["from_id"]
        if left == r.nid(10):
            r.edge_hold_reasons[e["id"]] = (
                "Elbow dislocation is described near fractures, but the source does not identify it as a fracture subtype. Co-location under a chapter heading does not prove IS_A."
            )
            continue
        if e["type"] == "MANAGED_BY":
            ranges = [(15, 0, 1), (15, 5, 6)]
            cond = "Sau gãy thấp trên lồi cầu, cẳng tay vẹo vào trong; phân biệt nắn kém với rối loạn phát triển theo nguồn"
        else:
            ranges = r.node_ranges[left]
            cond = None
        retained[e["id"]] = (ranges, cond)
    recovered = {
        (w1, "edge_2"): (
            r.nid(8),
            r.nid(12),
            "MANAGED_BY",
            [(12, 0, 3)],
            "Gãy gần một đầu xương phạm sụn phát triển, rối loạn phát triển với trục xương lệch vẹo; thường cần mổ sửa",
        ),
        (w2, "edge_1"): (r.nid(15), physis, "IS_A", [(15, 0, 6)]),
        (w2, "edge_2"): (r.nid(3), physis, "IS_A", [(15, 0, 5), (15, 6, 9)]),
        (w2, "edge_3"): (
            physis,
            r.nid(14),
            "MANAGED_BY",
            [(15, 0, 4)],
            "Ở đa số ca đường gãy nằm ở hành xương sát sụn phát triển; gây mê mềm cơ, nhẹ nhàng nắn đúng giải phẫu",
        ),
    }
    r.missing = [
        {
            "kind": "ambiguous_printed_claim",
            "pdf_pages": [13],
            "reason": "Bản in ghi “chỉ 1-2 ca, gãy lệch 1-2mm mới không mổ”; không có mẫu số/tỷ lệ rõ. Giữ ngoài phát biểu này, không tự chuyển thành phần trăm.",
            "sources": [r.source(13, 3, 4)],
        },
        {
            "kind": "uncertain_ocr_procedural_paragraph",
            "pdf_pages": [14],
            "reason": "Đoạn đinh nội tuỷ/vòng chỉ thép cần đọc lại chữ và kỹ thuật; chưa nhập nguyên đoạn OCR có lỗi. Bao gồm chỉ định theo vị trí, mốc 6 tháng và nguy cơ gãy lại.",
            "sources": [r.source(14, 6, 7)],
        },
        {
            "kind": "model_omitted_whole_bullets",
            "pdf_pages": [14],
            "reason": "Các loại gãy cẳng bàn tay; gãy cẳng/bàn chân; vỡ xương chậu/gãy cột sống chưa có node tương ứng trong output. Đưa vào extraction bổ sung, không tự sinh node.",
            "sources": [r.source(14, 2, 3), r.source(14, 11, 13)],
        },
        {
            "kind": "printed_figure_caption",
            "pdf_pages": [12, 13],
            "reason": "Hình 2.1/2.2 đã nhìn trực tiếp, caption thực được giữ trong audit; chỉ là tên hình, không coi là mô tả ảnh do AI tạo. Caption 2.2 hỗ trợ node lồi cầu ngoài; 2.1 ghi lồi cầu trong phần trên lồi cầu nên không ép chúng đồng nghĩa.",
            "sources": [r.source(12, 10, 11), r.source(13, 2, 3)],
        },
    ]
    r.finish(retained, recovered)


if __name__ == "__main__":
    lesson1()
    lesson2()
