"""Source comparison workbench for the remaining 2006 extraction, no LLM calls.

Prepare dossiers first. A separately authored, dossier-fingerprinted decision
file is required before compiling each chapter. Import uses the existing scoped
importer and a second idempotency pass. Original extraction stays read-only.
"""

import argparse
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
from knowledge_pipeline.kg_v2.neo4j_import import import_review, validate_locators

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/knowledge-extraction/v2/source-review-20261102"
WORK = OUT / "remaining-2006"
SID = "SRC_ORTHO_EMERGENCY_001"
PDF = (
    ROOT
    / "data/raw-source/data-20261020T074653Z-1-001/data/Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi.pdf"
)
PDF_HASH = "d95f9d803e46c1bb8b41a2b35fc53add5dd8959df1b3107a83f8e0c324469007"


def jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in values),
        encoding="utf-8",
    )


def load_chapter(number):
    row = next(
        r
        for r in read_json(OUT / "inventory.json")["chapters"]
        if r["book_year"] == 2006 and r["lesson_number"] == number
    )
    nodes = {}
    edges = {}
    pages = {}
    locators = {}
    blocks = {}
    held = {}
    mappings = {}
    for name in row["selected_sources"]:
        parent = ROOT / name
        graph = read_json(parent / "graph.json")
        nodes.update({r["id"]: r for r in graph["nodes"]})
        edges.update({r["id"]: r for r in graph["edges"]})
        locators.update(
            {r["locator_id"]: r for r in read_json(parent / "audit/locators.json")}
        )
        for p in map(
            json.loads,
            (parent / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines(),
        ):
            if row["pdf_pages"]["start"] <= p["pdf_page"] <= row["pdf_pages"]["end"]:
                pages[p["pdf_page"]] = p
        for window in read_json(parent / "audit/windows.json"):
            blocks.update({b["block_id"]: b for b in window["blocks"]})
        for filename in ["review_items.json", "rejected.json"]:
            for r in read_json(parent / "audit" / filename):
                if r.get("kind") in {"node", "edge"} and isinstance(
                    r.get("candidate"), dict
                ):
                    held[r.get("window_id"), r["kind"], r.get("local_id")] = r
        candidate_ids = read_json(parent / "audit/draft_id_mapping.json")
        for r in read_json(parent / "audit/identity_registry.json"):
            if r["candidate_id"] in candidate_ids:
                mappings[r["window_id"], r["local_id"]] = candidate_ids[
                    r["candidate_id"]
                ]
    return (
        row,
        list(nodes.values()),
        list(edges.values()),
        pages,
        locators,
        blocks,
        list(held.values()),
        mappings,
    )


def line_range(page, start, end):
    raw = page["raw_text"]
    lines = raw.splitlines(keepends=True)
    pos = 0
    found = []
    for index, line in enumerate(lines):
        if pos < end and pos + len(line) > start:
            found.append(index)
        pos += len(line)
    if not found:
        raise ValueError("empty_source_line_range")
    return [page["pdf_page"], found[0], found[-1] + 1]


def refs_for(sources, pages, locators):
    result = []
    for s in sources:
        loc = locators[s["locator_id"]]
        r = line_range(
            pages[loc["pdf_page"]], loc["raw_char_start"], loc["raw_char_end"]
        )
        if r not in result:
            result.append(r)
    return result


def prepare(number):
    row, nodes, edges, pages, locators, blocks, held, _ = load_chapter(number)
    folder = WORK / f"bai-{number:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    indices = {n["id"]: i for i, n in enumerate(nodes)}
    text = [
        f"BÀI {number}: {row['title']} — PDF {row['pdf_pages']}",
        "SOURCE LINES (raw OCR; AI image descriptions excluded only from this display):",
    ]
    for page, p in sorted(pages.items()):
        text.append(f"\nPAGE {page}")
        for i, line in enumerate(p["raw_text"].splitlines()):
            if not line.isascii() and not line.startswith(("This ", "The image ")):
                text.append(f"{page}.{i}: {line}")
    text.append("\nNODES — source line ranges [page,start,end-exclusive]")
    for i, n in enumerate(nodes):
        ss = n.get("sources", []) + [
            s for c in n.get("content", []) for s in c["sources"]
        ]
        text.append(
            f"N{i} {n['type']} | {n.get('name', n.get('text'))} | {refs_for(ss, pages, locators)}"
            + (
                " ALIASES=" + json.dumps(n["aliases"], ensure_ascii=False)
                if n.get("aliases")
                else ""
            )
        )
    text.append("\nEDGES")
    for i, e in enumerate(edges):
        text.append(
            f"E{i} N{indices[e['from_id']]} {e['type']} N{indices[e['to_id']]} | {e['condition']} | {refs_for(e['sources'], pages, locators)}"
        )
    text.append("\nHELD PROPOSALS (deduplicated by window/kind/local_id)")
    for i, h in enumerate(held):
        c = h["candidate"]
        supports = []
        if h["kind"] == "node":
            supports = (
                c.get("identity_sources", [])
                if isinstance(c.get("identity_sources", []), list)
                else []
            )
        else:
            supports = (
                c.get("sources", []) if isinstance(c.get("sources", []), list) else []
            )
        ranges = []
        for s in supports:
            if isinstance(s, dict) and s.get("block_id") in blocks:
                b = blocks[s["block_id"]]
                ranges.append(
                    line_range(pages[b["pdf_page"]], b["char_start"], b["char_end"])
                )
        name = c.get("name", f"{c.get('from_id')} {c.get('type')} {c.get('to_id')}")
        text.append(
            f"H{i} {h['kind']} {c.get('type')} | {name} | {h['reason']} | {ranges}"
        )
    dossier = "\n".join(text) + "\n"
    (folder / "dossier.txt").write_text(dossier, encoding="utf-8")
    write_json(
        folder / "input-manifest.json",
        {
            "lesson_number": number,
            "dossier_fingerprint": fingerprint(dossier),
            "nodes_fingerprint": fingerprint(nodes),
            "edges_fingerprint": fingerprint(edges),
            "parents": row["selected_sources"],
        },
    )
    return folder


def render(pages):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(PDF))
    for page in pages:
        path = WORK / f"pdf/{page}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            pdf_page = document[page - 1]
            bitmap = pdf_page.render(scale=1.8)
            bitmap.to_pil().save(path)


def compile_review(number, apply=False):
    (
        row,
        original_nodes,
        original_edges,
        original_pages,
        old_locs,
        _,
        held,
        _local_mapping,
    ) = load_chapter(number)
    folder = WORK / f"bai-{number:02d}"
    spec = read_json(folder / "decisions-input.json")
    manifest = read_json(folder / "input-manifest.json")
    dossier = (folder / "dossier.txt").read_text(encoding="utf-8")
    if (
        spec.get("dossier_fingerprint") != fingerprint(dossier)
        or spec.get("all_graph_records_read") is not True
    ):
        raise ValueError("explicit_complete_dossier_review_required")
    if (fingerprint(original_nodes), fingerprint(original_edges)) != (
        manifest["nodes_fingerprint"],
        manifest["edges_fingerprint"],
    ):
        raise ValueError("original_extraction_changed")
    target = OUT / f"chapters/2006-bai-{number:02d}"
    target.mkdir(parents=True, exist_ok=True)
    pages = {}
    patches = []
    locs = {}
    decisions = []
    pending = []
    idmap = {}
    node_map = {}
    edge_map = {}
    for page, original in original_pages.items():
        p = copy.deepcopy(original)
        raw = p["raw_text"]
        corrected = ""
        segments = []
        offset = 0
        for line_no, line in enumerate(raw.splitlines(keepends=True)):
            before = line.rstrip("\r\n")
            ending = line[len(before) :]
            after = before
            patch_id = None
            change = spec.get("ocr", {}).get(f"{page}.{line_no}")
            if change:
                if page not in spec.get("pdf_viewed", []):
                    raise ValueError("ocr_patch_requires_actually_viewed_pdf")
                after = change
                patch_id = f"REVIEW2006_{page}_{line_no}"
                changed_markers = protected_markers(before) != protected_markers(after)
                if changed_markers and f"{page}.{line_no}" not in spec.get(
                    "printed_marker_restorations", []
                ):
                    raise ValueError(
                        f"numeric_or_negation_change_not_explicitly_reviewed_{page}_{line_no}"
                    )
                image = WORK / f"pdf/{page}.png"
                patches.append(
                    {
                        "id": patch_id,
                        "pdf_page": page,
                        "raw_start": offset,
                        "raw_end": offset + len(before),
                        "before": before,
                        "after": after,
                        "numeric_or_negation_markers_changed": changed_markers,
                        "decision": "visual_pdf_transcription",
                        "source_pdf_sha256": PDF_HASH,
                        "image_path": image.relative_to(ROOT).as_posix(),
                        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    }
                )
            segments.append(
                {
                    "raw_start": offset,
                    "raw_end": offset + len(before),
                    "corrected_start": len(corrected),
                    "corrected_end": len(corrected) + len(after),
                    "patch_id": patch_id,
                }
            )
            corrected += after
            if ending:
                segments.append(
                    {
                        "raw_start": offset + len(before),
                        "raw_end": offset + len(line),
                        "corrected_start": len(corrected),
                        "corrected_end": len(corrected) + len(ending),
                        "patch_id": None,
                    }
                )
                corrected += ending
            offset += len(line)
        p["text"] = corrected
        p["correction"] = {
            "raw_text": raw,
            "corrected_text": corrected,
            "segments": segments,
            "patch_ids": [r["id"] for r in patches if r["pdf_page"] == page],
            "revision": fingerprint([raw, corrected, segments]),
            "expert_review": "unverified",
        }
        pages[page] = p

    def source(r):
        page, start_line, end_line = r
        p = pages[page]
        lines = p["text"].splitlines(keepends=True)
        start = sum(map(len, lines[:start_line]))
        end = sum(map(len, lines[:end_line]))
        excerpt = p["text"][start:end].rstrip("\r\n")
        end = start + len(excerpt)
        lid = (
            "LOCR_"
            + fingerprint([SID, page, start, end, p["correction"]["revision"]])[:24]
        )
        locs[lid] = {
            "locator_id": lid,
            "source_id": SID,
            "document_edition_id": p["document_edition_id"],
            "source_sha256": PDF_HASH,
            "ocr_sha256": p["ocr_sha256"],
            "pdf_page": page,
            "char_start": start,
            "char_end": end,
            "corrected_char_start": start,
            "corrected_char_end": end,
            "text": excerpt,
            **trace_raw(p["correction"], start, end),
        }
        return {
            "source_id": SID,
            "locator_id": lid,
            "pdf_pages": [page],
            "printed_pages": [str(page - 1)],
            "excerpt": excerpt,
        }

    def contents(ranges):
        ss = [source(r) for r in ranges]
        return [{"text": "\n".join(s["excerpt"] for s in ss), "sources": ss}]

    nodes = {}
    node_ranges = {}
    for index, before in enumerate(original_nodes):
        key = f"N{index}"
        action = spec.get("nodes", {}).get(key, {})
        n = copy.deepcopy(before)
        reason = action.get(
            "reason",
            "Đã đọc đối tượng, phạm vi và đoạn nguồn; giữ nội dung theo nguồn. Alias không có dẫn chứng riêng được bỏ trong overlay.",
        )
        if action.get("hold"):
            d = {
                "kind": "node",
                "id": n["id"],
                "ordinal": key,
                "decision": "hold",
                "before": before,
                "after": None,
                "reason": reason,
            }
            pending.append(d)
            decisions.append(d)
            continue
        if "merge_into" in action:
            target_id = original_nodes[int(action["merge_into"][1:])]["id"]
            idmap[n["id"]] = target_id
            decisions.append(
                {
                    "kind": "node",
                    "id": n["id"],
                    "ordinal": key,
                    "decision": "merge",
                    "before": before,
                    "kept_id": target_id,
                    "reason": reason,
                }
            )
            continue
        if action.get("canonical_id"):
            registry = read_json(
                ROOT / "knowledge_pipeline/kg_v2/canonical-registry.json"
            )
            if action["canonical_id"] not in registry["entities"]:
                raise ValueError("unknown_confirmed_canonical_identity")
            idmap[n["id"]] = action["canonical_id"]
            n["id"] = action["canonical_id"]
        if n.get("content"):
            groups = action.get("content_groups") or (
                [action["ranges"]]
                if action.get("ranges")
                else [
                    refs_for(c["sources"], original_pages, old_locs)
                    for c in n["content"]
                ]
            )
            n["content"] = [contents(group)[0] for group in groups]
            node_ranges[n["id"]] = [r for group in groups for r in group]
        if n["type"] == "SampleQuestion":
            n["sources"] = [
                source(r) for r in refs_for(n["sources"], original_pages, old_locs)
            ]
            n["answer_sources"] = [
                source(r)
                for r in refs_for(n["answer_sources"], original_pages, old_locs)
            ]
        if "name" in action:
            n["name"] = action["name"]
        if "type" in action:
            n["type"] = action["type"]
        if "aliases" in n:
            n["aliases"] = action.get("aliases", [])
        if n["id"] in nodes:
            raise ValueError("explicit_merge_required")
        nodes[n["id"]] = n
        node_map[key] = n["id"]
        decisions.append(
            {
                "kind": "node",
                "ordinal": key,
                "id": before["id"],
                "decision": "correct" if n != before else "keep",
                "before": before,
                "after": n,
                "reason": reason,
            }
        )
    for old in list(idmap):
        while idmap[old] in idmap:
            idmap[old] = idmap[idmap[old]]
    for index, n in enumerate(original_nodes):
        if n["id"] in idmap:
            node_map[f"N{index}"] = idmap[n["id"]]
    for index, item in enumerate(held):
        key = f"H{index}"
        action = spec.get("held", {}).get(key, {})
        if item["kind"] == "node" and action.get("merge_into"):
            identifier = node_map[action["merge_into"]]
            node_map[key] = identifier
            decisions.append(
                {
                    "kind": "node",
                    "ordinal": key,
                    "decision": "merge_recovered",
                    "before": item["candidate"],
                    "after": nodes[identifier],
                    "reason": action["reason"],
                }
            )
            continue
        if not action.get("recover"):
            d = {
                "kind": item["kind"],
                "ordinal": key,
                "decision": "hold",
                "before": item["candidate"],
                "after": None,
                "window_id": item.get("window_id"),
                "local_id": item.get("local_id"),
                "reason": action.get(
                    "reason",
                    f"Giữ ngoài theo audit {item['reason']}; đối tượng/quote/cấu trúc/quan hệ chưa chứng minh được đầy đủ trong phạm vi nguồn, không tự lấp chỗ thiếu.",
                ),
            }
            pending.append(d)
            decisions.append(d)
            continue
        if item["kind"] != "node":
            continue
        n = copy.deepcopy(item["candidate"])
        identifier = (
            action.get("canonical_id")
            or "DRN_"
            + uuid5(
                NAMESPACE_URL,
                f"medresident:review2006:{item.get('window_id')}:{item.get('local_id')}",
            ).hex
        )
        n = {
            "id": identifier,
            "type": action.get("type", n["type"]),
            "name": action.get("name", n.get("name")),
            "aliases": [],
            "content": contents(action["ranges"]),
        }
        if n["type"] == "Skill":
            n.pop("aliases")
            n["kind"] = action["kind"]
        nodes[identifier] = n
        node_map[key] = identifier
        node_ranges[identifier] = action["ranges"]
        decisions.append(
            {
                "kind": "node",
                "ordinal": key,
                "decision": "recover",
                "before": item["candidate"],
                "after": n,
                "reason": action["reason"],
            }
        )
    edges = {}
    seen = {}

    def add_edge(before, action, key, kind="edge"):
        e = copy.deepcopy(before)
        if action.get("hold"):
            d = {
                "kind": kind,
                "ordinal": key,
                "decision": "hold",
                "before": before,
                "after": None,
                "reason": action["reason"],
            }
            pending.append(d)
            decisions.append(d)
            return
        for field in ["from_id", "to_id"]:
            e[field] = idmap.get(e[field], e[field])
        if "from" in action:
            e["from_id"] = node_map[action["from"]]
        if "to" in action:
            e["to_id"] = node_map[action["to"]]
        if "type" in action:
            e["type"] = action["type"]
        if "condition" in action:
            e["condition"] = action["condition"]
        if (
            e["from_id"] not in nodes
            or e["to_id"] not in nodes
            or e["from_id"] == e["to_id"]
        ):
            d = {
                "kind": kind,
                "ordinal": key,
                "decision": "hold",
                "before": before,
                "after": None,
                "reason": "Đầu mút đã giữ ngoài hoặc self-loop sau merge; không tự thay node khác.",
            }
            pending.append(d)
            decisions.append(d)
            return
        ranges = action.get("ranges") or refs_for(
            e["sources"], original_pages, old_locs
        )
        e["sources"] = [source(r) for r in ranges]
        signature = (e["from_id"], e["to_id"], e["type"], e.get("condition"))
        if signature in seen:
            kept = edges[seen[signature]]
            for s in e["sources"]:
                if s not in kept["sources"]:
                    kept["sources"].append(s)
            edge_map[e["id"]] = kept["id"]
            decision = "merge"
        else:
            edges[e["id"]] = e
            seen[signature] = e["id"]
            decision = "correct" if e != before else "keep"
        decisions.append(
            {
                "kind": kind,
                "ordinal": key,
                "decision": decision,
                "before": before,
                "after": e,
                "reason": action.get(
                    "reason",
                    "Đã đọc hai đầu, chiều, loại và điều kiện trong đoạn nguồn; quote được giữ nguyên cả dòng nguồn để không cắt phủ định.",
                ),
            }
        )

    for index, before in enumerate(original_edges):
        add_edge(before, spec.get("edges", {}).get(f"E{index}", {}), f"E{index}")
    for index, item in enumerate(held):
        key = f"H{index}"
        action = spec.get("held", {}).get(key, {})
        if item["kind"] == "edge" and action.get("recover"):
            before = {
                "id": "DRE_"
                + fingerprint(
                    ["review2006", number, item["window_id"], item["local_id"]]
                )[:24],
                "from_id": node_map[action["from"]],
                "to_id": node_map[action["to"]],
                "type": action.get("type", item["candidate"]["type"]),
                "condition": action.get(
                    "condition", item["candidate"].get("condition")
                ),
                "sources": [],
            }
            add_edge(before, action, key)
            decisions[-1]["before"] = item["candidate"]
            if decisions[-1]["decision"] != "hold":
                decisions[-1]["decision"] = "recover"
    graph = {
        "schema_version": "medical-kg-v2",
        "nodes": sorted(nodes.values(), key=lambda r: r["id"]),
        "edges": sorted(edges.values(), key=lambda r: r["id"]),
    }
    dry_run_loader(graph)
    if (
        (target / "review-manifest.json").exists()
        and any(target.glob("import-*/import-manifest.json"))
        and read_json(target / "review-manifest.json")["graph_fingerprint"]
        != fingerprint(graph)
    ):
        raise ValueError("already_imported_overlay_is_immutable")
    write_json(target / "graph.json", graph)
    jsonl(target / "reviewed-nodes.jsonl", graph["nodes"])
    jsonl(target / "reviewed-edges.jsonl", graph["edges"])
    jsonl(target / "audit/pages.jsonl", pages.values())
    write_json(target / "audit/locators.json", list(locs.values()))
    write_json(target / "ocr-patches.json", patches)
    write_json(target / "decisions.json", decisions)
    write_json(target / "pending-review.json", pending)
    write_json(target / "rejected.json", [d for d in pending])
    write_json(
        target / "id-mapping.json",
        {
            "node_remap": idmap,
            "edge_remap": edge_map,
            "local_to_stable": [{"ordinal": k, "id": v} for k, v in node_map.items()],
        },
    )
    write_json(target / "need-extraction.json", spec.get("missing", []))
    checked = validate_locators(graph, target)
    m = {
        "book_year": 2006,
        "lesson_number": number,
        "title": row["title"],
        "review_status": "source_compared_records_separated",
        "graph_fingerprint": fingerprint(graph),
        "nodes_before": len(original_nodes),
        "edges_before": len(original_edges),
        "nodes_after": len(nodes),
        "edges_after": len(edges),
        "pending_records": len(pending),
        "missing_content_items": len(spec.get("missing", [])),
        "decisions": dict(Counter(d["decision"] for d in decisions)),
        "pdf_actually_viewed": spec.get("pdf_viewed", []),
        "ocr_pages_read_in_dossier": sorted(pages),
        "pdf_text_compared": spec.get("pdf_text_compared", []),
        "quote_and_raw_trace_checked_locators": checked,
        "expert_verified": False,
        "new_llm_calls": 0,
        "ocr_patch_count": len(patches),
        "parents": row["selected_sources"],
        "review_input": (folder / "decisions-input.json").relative_to(ROOT).as_posix(),
    }
    write_json(target / "review-manifest.json", m)
    names = {n["id"]: n.get("name", n.get("text", "")) for n in graph["nodes"]}
    cards = [
        '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Review sách 2006</title><style>body{font:16px system-ui;max-width:1080px;margin:30px auto;padding:0 16px}pre{white-space:pre-wrap}article{border-top:1px solid #ddd;padding:12px 0}summary{cursor:pointer}small{color:#555}</style>',
        f"<h1>Bài {number}: {html.escape(row['title'])}</h1>",
        "<p>Đã đọc toàn bộ node/cạnh và nguồn OCR trong dossier. Chưa phải chuyên gia y khoa duyệt. PDF ảnh đã xem: "
        + str(spec.get("pdf_viewed", []))
        + ". Đối chiếu text PDF bằng code: "
        + str(spec.get("pdf_text_compared", []))
        + ".</p>",
        "<h2>Cần quyết định / còn thiếu</h2>",
        "<p>"
        + str(len(pending))
        + ' đề xuất ngoài graph. <a href="pending-review.json">Chi tiết</a> · <a href="need-extraction.json">Phần thiếu</a> · <a href="decisions.json">Trước/sau</a></p>',
    ]
    for d in pending:
        cards += [
            "<details><summary>"
            + html.escape(
                d["before"].get(
                    "name",
                    d["before"].get("local_id", d["before"].get("id", "Đề xuất")),
                )
            )
            + "</summary><p>"
            + html.escape(d["reason"])
            + "</p></details>"
        ]
    cards += ["<h2>Nội dung đã kiểm tra</h2>"]
    md = [
        f"# Bài {number}: {row['title']}",
        "",
        f"Node {len(original_nodes)} → {len(nodes)}; cạnh {len(original_edges)} → {len(edges)}. Giữ ngoài {len(pending)}.",
        "",
        str(spec.get("review_notes", "")),
        "",
    ]
    for n in graph["nodes"]:
        cards += [
            "<article><h3>"
            + html.escape(names[n["id"]])
            + " <small>"
            + n["type"]
            + "</small></h3>"
        ]
        md += [f"## {names[n['id']]} ({n['type']})", ""]
        for c in n.get("content", []):
            cards += [
                "<pre>"
                + html.escape(c["text"])
                + "</pre><small>Nguồn: "
                + ", ".join("PDF " + str(s["pdf_pages"][0]) for s in c["sources"])
                + "</small>"
            ]
            md += [
                c["text"],
                "",
                "Nguồn: " + str([s["pdf_pages"] for s in c["sources"]]),
                "",
            ]
        for e in graph["edges"]:
            if e["from_id"] == n["id"]:
                cards += [
                    "<p>"
                    + e["type"]
                    + " → "
                    + html.escape(names[e["to_id"]])
                    + "; "
                    + html.escape(e.get("condition") or "")
                    + "</p><details><summary>Nguồn cạnh</summary><pre>"
                    + html.escape("\n".join(s["excerpt"] for s in e["sources"]))
                    + "</pre></details>"
                ]
                md += [f"- {e['type']} → {names[e['to_id']]}: {e.get('condition')}"]
        cards += ["</article>"]
    (target / "review.html").write_text("\n".join(cards) + "</html>", encoding="utf-8")
    (target / "review.md").write_text("\n".join(md), encoding="utf-8")
    if apply:
        progress = read_json(OUT / "progress.json")
        previous = progress["chapters"].get(target.name, {})
        if previous.get("import_status") != "imported_and_idempotency_verified":
            index = 1
            while (target / f"import-{index:03d}").exists() or (
                target / f"import-{index + 1:03d}"
            ).exists():
                index += 1
            first = import_review(
                target / "graph.json", target / f"import-{index:03d}", apply=True
            )
            second = import_review(
                target / "graph.json", target / f"import-{index + 1:03d}", apply=True
            )
            if any(
                second["counts"][k].get(a, 0)
                for k in ["nodes", "edges"]
                for a in ["create", "update"]
            ):
                raise ValueError("idempotency_failed")
            progress["chapters"][target.name] = {
                **m,
                "review_directory": target.relative_to(ROOT).as_posix(),
                "import_status": "imported_and_idempotency_verified",
                "first_import": first["counts"],
                "second_import": second["counts"],
                "first_manifest": (target / f"import-{index:03d}/import-manifest.json")
                .relative_to(ROOT)
                .as_posix(),
                "idempotency_manifest": (
                    target / f"import-{index + 1:03d}/import-manifest.json"
                )
                .relative_to(ROOT)
                .as_posix(),
            }
            write_json(OUT / "progress.json", progress)
            m["import_counts"] = first["counts"]
            m["idempotency_counts"] = second["counts"]
    print(json.dumps(m, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", type=int, nargs="+")
    parser.add_argument("--render", type=int, nargs="+")
    parser.add_argument("--compile", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    for number in args.prepare or []:
        print(prepare(number))
    if args.render:
        render(args.render)
    if args.compile:
        compile_review(args.compile, args.apply)


if __name__ == "__main__":
    main()
