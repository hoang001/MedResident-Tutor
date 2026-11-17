"""Conservative offline source audit of the existing 2021 draft, no LLM calls.

Exact OCR provenance checks run on every record. Semantic edge decisions and
PDF image observations are explicit review inputs, never inferred from schema.
Unresolved original proposals remain outside the imported graph.
"""

import argparse
import copy
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.corrections import protected_markers, trace_raw
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import import_review, validate_locators
from scripts import decisions_2021_book as decisions

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/knowledge-extraction/v2/source-review-20261102-2021"
BATCH = ROOT / "data/knowledge-extraction/v2/book-2021-full-wait"
SOURCE = BATCH / "aggregate-0001"
PDF = ROOT / "data/raw-source/DVC.005844.pdf"
PLAN = ROOT / "knowledge_pipeline/kg_v2/book-2021-all-lessons-plan.json"


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def norm(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold()))


def refs(row):
    return (
        row.get("sources", [])
        + row.get("answer_sources", [])
        + [s for c in row.get("content", []) for s in c["sources"]]
    )


def inputs():
    graph = read_json(SOURCE / "graph.json")
    pages = {
        r["pdf_page"]: r
        for r in map(
            json.loads,
            (SOURCE / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    locators = {r["locator_id"]: r for r in read_json(SOURCE / "audit/locators.json")}
    plan = read_json(PLAN)
    return graph, pages, locators, plan


def chapter_for(row, plan):
    pages = {p for s in refs(row) for p in s["pdf_pages"] if p >= 8}
    found = [
        c["lesson_number"]
        for c in plan["chapters"]
        if any(c["pdf_pages"]["start"] <= p <= c["pdf_pages"]["end"] for p in pages)
    ]
    return found[0] if len(found) == 1 else None


def node_check(n, pages, locators, plan):
    reasons = []
    scope = chapter_for(n, plan)
    if scope is None:
        reasons.append("missing_or_cross_chapter_scope")
    try:
        for s in refs(n):
            loc = locators[s["locator_id"]]
            p = pages[loc["pdf_page"]]
            if (
                p["text"][loc["char_start"] : loc["char_end"]] != s["excerpt"]
                or p["raw_text"][loc["raw_char_start"] : loc["raw_char_end"]]
                != loc["raw_text"]
            ):
                reasons.append("exact_quote_or_raw_offset_mismatch")
            if s["source_id"] != plan["source_id"] or s["pdf_pages"] != [
                loc["pdf_page"]
            ]:
                reasons.append("source_or_page_mismatch")
        for c in n.get("content", []):
            if c["text"] != "\n".join(s["excerpt"] for s in c["sources"]):
                reasons.append("content_not_exact_quotes")
    except (KeyError, TypeError):
        reasons.append("unresolvable_provenance")
    text = "\n".join(s["excerpt"] for s in refs(n))
    name = n.get("name", n.get("text", ""))
    if n["type"] != "SampleQuestion" and norm(name) not in norm(text):
        reasons.append("identity_not_literal_in_own_source_requires_semantic_review")
    if n["type"] == "SampleQuestion" and (
        norm(n["text"]) not in norm(text)
        or any(norm(o) not in norm(text) for o in n["options"])
    ):
        reasons.append("question_or_options_not_verbatim")
    if n["type"] in ["Condition", "Finding"] and re.search(
        r"^(Clostridium|Staphylococcus|Streptococcus|Vi khuẩn|Tụ cầu vàng|Trực khuẩn|Virus|Vi rút)",
        name,
        re.IGNORECASE,
    ):
        reasons.append("microorganism_not_a_condition_or_patient_finding")
    if n["type"] == "Drug" and re.search(
        r"\b(chỉ khâu|đinh|nẹp|kim|khung|ống thông|vít|Prolen|Kirschner|catheter)\b",
        name,
        re.IGNORECASE,
    ):
        reasons.append("device_or_material_not_drug")
    if n["type"] == "ClinicalPrinciple" and not re.search(
        r"\b(phải|cần|nên|không được|nguyên tắc|chỉ định|chống chỉ định)\b",
        text,
        re.IGNORECASE,
    ):
        reasons.append("descriptive_heading_not_established_clinical_principle")
    if n["type"] == "Condition" and re.fullmatch(
        r"(Biến chứng|Di chứng|Triệu chứng|Lâm sàng|Điều trị|Phân loại|Dịch tễ học)( .*)?",
        name,
        re.IGNORECASE,
    ):
        reasons.append("abstract_section_not_independent_condition")
    if n["type"] == "Skill":
        reasons.append("skill_basis_requires_explicit_review")
    if n.get("content") and all(len(c["text"].strip()) < 35 for c in n["content"]):
        reasons.append("heading_or_thin_content_requires_expansion_review")
    return scope, sorted(set(reasons))


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    graph, pages, locators, plan = inputs()
    baseline = OUT / "audit/protected-hashes.json"
    if not baseline.exists():
        paths = [p for p in BATCH.rglob("*") if p.is_file()]
        paths += [PDF, ROOT / plan["ocr_input"], PLAN]
        paths += list((ROOT / "knowledge_pipeline/kg_v2").glob("*.py"))
        paths += [
            ROOT / "knowledge_pipeline/kg_v2/canonical-registry.json",
            ROOT
            / "data/knowledge-extraction/v2/source-review-20261102/combined/graph.json",
        ]
        write_json(
            baseline,
            {
                p.relative_to(ROOT).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in paths
            },
        )
    index = []
    by_id = {n["id"]: n for n in graph["nodes"]}
    for i, n in enumerate(graph["nodes"]):
        chapter, reasons = node_check(n, pages, locators, plan)
        index.append(
            {"ordinal": f"N{i}", "id": n["id"], "chapter": chapter, "reasons": reasons}
        )
    write_json(OUT / "audit/node-checks.json", index)
    for c in plan["chapters"]:
        number = c["lesson_number"]
        rows = [r for r in index if r["chapter"] == number]
        ids = {r["id"] for r in rows}
        edges = [
            (i, e)
            for i, e in enumerate(graph["edges"])
            if e["from_id"] in ids or e["to_id"] in ids
        ]
        dossier = [
            f"Bài {number}: {c['title']} PDF{c['pdf_pages']}",
            "NODES: ordinal | type | name | source excerpt (first200chars) | flags",
        ]
        for r in rows:
            n = by_id[r["id"]]
            text = " / ".join(c["text"] for c in n.get("content", []))
            dossier.append(
                f"{r['ordinal']} {n['type']} {n.get('name', n.get('text'))} | {text[:200]} | {','.join(r['reasons'])}"
            )
        dossier += [
            "EDGES: ordinal | from | type | to | condition | exact supporting quote"
        ]
        for i, e in edges:
            left, right = by_id[e["from_id"]], by_id[e["to_id"]]
            quote = " / ".join(s["excerpt"] for s in e["sources"])
            dossier.append(
                f"E{i} {left.get('name', left.get('text'))} [{left['type']}] {e['type']} {right.get('name', right.get('text'))} [{right['type']}] | {e.get('condition')} | {quote}"
            )
        folder = OUT / f"chapters/2021-bai-{number:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "dossier.txt").write_text("\n".join(dossier), encoding="utf-8")
        write_json(
            folder / "input.json",
            {
                "chapter": c,
                "nodes": rows,
                "edge_ordinals": [f"E{i}" for i, e in edges],
                "dossier_fingerprint": fingerprint(dossier),
                "source_graph_fingerprint": fingerprint(graph),
            },
        )
    # The pre-existing review/rejected items are NOT silently approved or recovered.
    report = read_json(SOURCE / "audit/report.json")
    write_json(
        OUT / "audit/extraction-status.json",
        {
            k: v
            for k, v in report.items()
            if k
            in [
                "status",
                "windows_total",
                "windows_with_raw_output",
                "failed_windows",
                "partial_schema_windows",
                "draft_nodes",
                "draft_edges",
                "review_items",
                "rejected_items",
            ]
        },
    )
    write_json(
        OUT / "audit/original-held-index.json",
        {
            "review_items": (SOURCE / "review-items.jsonl")
            .relative_to(ROOT)
            .as_posix(),
            "rejected_items": (SOURCE / "rejected-items.jsonl")
            .relative_to(ROOT)
            .as_posix(),
            "status": "outside_graph_not_source_or_semantically_approved",
        },
    )
    state = read_json(BATCH / "batch-state.json")
    failed = []
    for name, r in state["shards"].items():
        for w in r.get("failed_windows", []):
            failed.append({"shard": name, **w})
    write_json(
        OUT / "missing-extraction.json",
        {
            "failed_windows": failed,
            "source_gaps": plan["source_gaps"],
            "new_llm_calls": 0,
        },
    )
    print(
        json.dumps(
            {
                "nodes": len(index),
                "nodes_literal_and_provenance_gate": sum(
                    not r["reasons"] for r in index
                ),
                "edges": len(graph["edges"]),
                "reasons": dict(Counter(x for r in index for x in r["reasons"])),
                "chapters": len(plan["chapters"]),
            },
            ensure_ascii=True,
        )
    )


def render(numbers):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(PDF)
    for number in numbers:
        target = OUT / f"pdf/{number}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            pdf[number - 1].render(scale=1.8).to_pil().save(target)


OCR_FLAGS = re.compile(
    r"đau chới|tự máu|lao xạ|xương xấp|vít xấp|mở cần|mũ quanh|mũ dưới|mũ cạnh|"
    r"viêm mũ|dẫn lưu mù|mâm chân|mầm chảy|màng chày|máu chuyển|xương đơn|"
    r"điểm bám.*chỏ cánh|sụn viên|ổ chỏ|chỏm và chỏm|gãy xương hông|gãy hờ|gây hỗ|"
    r"vết bóng|vết bồng|điều trị bóng|bóng độ|bóng sâu|bóng rộng|steo|sưng sâu|sưng nông|"
    r"vật da|chuyển vật|bao dày thần kinh|gân đuôi|đuôi gối|đuổi gói|gấp đuôi|"
    r"nẹp ép.*thép|gờ dính|xo dính|chân đỏ ngoài|khép dài|liệt tụy|sốc tụy|"
    r"thiếu sãn|thiếu sàn|cò sủng|đính ngón|chính hình|chính trục|tiền triển|"
    r"phần xạ|phân xạ|đột đội|đột trục|mòm răng|mòm rặng|thần kinh mắc|"
    r"chòm|khớp gót|khớp gói|chè dùi|chày dùi|lời cầu|lối cầu|"
    r"nghỉ ngơi tổn thương|khi nghỉ ngơi hoặc|gây mầm|gây hai xương|"
    r"tỷ lệ sớm|chịu tỷ lệ|gãy vít chót|gãy môi đinh|khuyết hông|dễ lười|"
    r"đuôi gói|gây ít lệch|diễn hình|kéo dài quá gây|cơ thất thanh môn|Những thở",
    re.IGNORECASE,
)
QUANTITATIVE = re.compile(
    r"\d\s*(?:%|°|\^|độ\b|mm\b|cm\b|mg\b|ml\b|kg\b|g/|giờ\b|tiếng\b|ngày\b|tuần\b|tháng\b|tuổi\b)|"
    r"(?:độ|loại|nhóm|typ|type|cơ lực)\s*(?:từ\s*)?\d|[<>≤≥]",
    re.IGNORECASE,
)
DOSE = re.compile(
    r"\d(?:[.,]\d+)?\s*(?:mg\b|ml\b|µg|μg|UI\b|IU\b|g/kg|g/ngày)", re.IGNORECASE
)


def quote_flags(s):
    reasons = []
    if OCR_FLAGS.search(s["excerpt"]):
        reasons.append("unresolved_medically_relevant_ocr")
    if re.search(r"[\u3400-\u9fff]", s["excerpt"]):
        reasons.append("unresolved_non_latin_ocr_artifact")
    if min(s["pdf_pages"]) >= 423 and re.search(
        r"xương dài", s["excerpt"], re.IGNORECASE
    ):
        reasons.append("long_bone_or_femur_ocr_ambiguity_requires_review")
    if DOSE.search(s["excerpt"]):
        reasons.append("dose_or_volume_requires_dedicated_pdf_verification")
    elif (
        QUANTITATIVE.search(s["excerpt"])
        and not set(s["pdf_pages"]) <= decisions.PDF_VIEWED
    ):
        reasons.append("quantitative_quote_not_yet_visually_verified")
    return reasons


def assert_protected():
    baseline = read_json(OUT / "audit/protected-hashes.json")
    changed = [
        name
        for name, digest in baseline.items()
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
    ]
    if changed:
        raise ValueError("protected_source_changed")
    return len(baseline)


def correction_char_map(page):
    result = [None] * len(page["text"])
    for segment in page["correction"]["segments"]:
        for pos in range(segment["corrected_start"], segment["corrected_end"]):
            if segment["patch_id"]:
                result[pos] = (
                    segment["raw_start"],
                    segment["raw_end"],
                    (segment["patch_id"],),
                )
            else:
                start = segment["raw_start"] + pos - segment["corrected_start"]
                result[pos] = (start, start + 1, ())
    if any(r is None for r in result):
        raise ValueError("upstream_correction_mapping_incomplete")
    return result


def compose_correction(page, mapping):
    segments = []
    for pos, (start, end, ids) in enumerate(mapping):
        prior = segments[-1] if segments else None
        if prior and not ids and not prior["patch_id"] and prior["raw_end"] == start:
            prior["raw_end"] = end
            prior["corrected_end"] = pos + 1
        elif (
            prior
            and ids
            and (prior["raw_start"], prior["raw_end"], prior["lineage_patch_ids"])
            == (start, end, list(ids))
        ):
            prior["corrected_end"] = pos + 1
        else:
            segments.append(
                {
                    "raw_start": start,
                    "raw_end": end,
                    "corrected_start": pos,
                    "corrected_end": pos + 1,
                    "patch_id": ("COMPOSED_" + fingerprint(ids)[:24]) if ids else None,
                    "lineage_patch_ids": list(ids),
                }
            )
    upstream = page["correction"]
    page["upstream_correction"] = upstream
    page["correction"] = {
        "raw_text": page["raw_text"],
        "corrected_text": page["text"],
        "segments": segments,
        "patch_ids": sorted({s["patch_id"] for s in segments if s["patch_id"]}),
        "revision": fingerprint([upstream["revision"], segments, page["text"]]),
        "upstream_revision": upstream["revision"],
        "expert_review": "unverified",
    }


def visual_overlays(graph, pages, locators):
    """Compose explicit PDF-confirmed edits over existing text; retain raw spans."""
    patches = []
    for pn, replacements in decisions.PAGE_REPLACEMENTS.items():
        if pn not in decisions.PDF_VIEWED:
            raise ValueError("patch_without_image_review")
        proof = OUT / f"pdf/{pn}.png"
        proof_hash = hashlib.sha256(proof.read_bytes()).hexdigest()
        page = pages[pn]
        mapping = correction_char_map(page)
        for before, after in replacements:
            if protected_markers(before) != protected_markers(after):
                raise ValueError("patch_changes_numeric_or_negation")
            positions = [
                m.start() for m in re.finditer(re.escape(before), page["text"])
            ]
            if not positions:
                raise ValueError("explicit_patch_literal_not_found")
            for start in reversed(positions):
                end = start + len(before)
                delta = len(after) - len(before)
                patch_id = "PDF2021_" + fingerprint([pn, start, before, after])[:24]
                touched = mapping[start:end]
                raw_start = min(r[0] for r in touched)
                raw_end = max(r[1] for r in touched)
                lineage = tuple(sorted({patch_id} | {k for r in touched for k in r[2]}))
                mapping[start:end] = [(raw_start, raw_end, lineage)] * len(after)
                for loc in locators.values():
                    if loc["pdf_page"] != pn:
                        continue
                    a, b = loc["char_start"], loc["char_end"]
                    if start < a < end or start < b < end:
                        raise ValueError("patch_crosses_quote_boundary")
                    if a >= end:
                        loc["char_start"] += delta
                    if b >= end:
                        loc["char_end"] += delta
                    if a < end and b > start:
                        loc.setdefault("visual_overlay_patch_ids", []).append(patch_id)
                page["text"] = page["text"][:start] + after + page["text"][end:]
                patches.append(
                    {
                        "id": patch_id,
                        "pdf_page": pn,
                        "input_text_start": start,
                        "before": before,
                        "after": after,
                        "decision": "confirmed_visual_transcription",
                        "image_path": proof.relative_to(ROOT).as_posix(),
                        "image_sha256": proof_hash,
                    }
                )
        compose_correction(page, mapping)
    remap = {}
    updated = {}
    for old, loc in locators.items():
        p = pages[loc["pdf_page"]]
        quote = p["text"][loc["char_start"] : loc["char_end"]]
        if loc["pdf_page"] in decisions.PAGE_REPLACEMENTS:
            loc["locator_id"] = (
                "LOC2021_"
                + fingerprint([old, loc["char_start"], loc["char_end"], quote])[:24]
            )
            loc["text"] = quote
            if "corrected_text" in loc:
                loc["corrected_text"] = quote
            loc["corrected_char_start"] = loc["char_start"]
            loc["corrected_char_end"] = loc["char_end"]
            trace = trace_raw(p["correction"], loc["char_start"], loc["char_end"])
            for key in ["raw_char_start", "raw_char_end", "raw_text"]:
                if trace[key] != loc[key]:
                    raise ValueError("composed_correction_raw_trace_changed")
            loc["upstream_correction_revision"] = loc["correction_revision"]
            loc["upstream_patch_ids"] = loc["patch_ids"]
            loc.update(trace)
            loc["visual_overlay_revision"] = fingerprint(patches)
        remap[old] = loc["locator_id"]
        updated[loc["locator_id"]] = loc
    for row in graph["nodes"] + graph["edges"]:
        for s in refs(row):
            s["locator_id"] = remap[s["locator_id"]]
            loc = updated[s["locator_id"]]
            s["excerpt"] = pages[loc["pdf_page"]]["text"][
                loc["char_start"] : loc["char_end"]
            ]
        for c in row.get("content", []):
            c["text"] = "\n".join(s["excerpt"] for s in c["sources"])
    for i, name in decisions.VISUAL_NODE_NAMES.items():
        graph["nodes"][i]["name"] = name
    write_json(OUT / "audit/visual-ocr-patches.json", patches)
    return graph, pages, updated


def compile_review():
    assert_protected()
    graph, pages, locators, plan = inputs()
    original_locators_checked = validate_locators(graph, SOURCE)
    graph, pages, locators = visual_overlays(graph, pages, locators)
    if decisions.REVIEWED_CHAPTERS != {c["lesson_number"] for c in plan["chapters"]}:
        raise ValueError("chapter_review_incomplete")
    checks = read_json(OUT / "audit/node-checks.json")
    node_audit, block_audit, nodes = [], [], {}
    for i, original in enumerate(graph["nodes"]):
        row = copy.deepcopy(original)
        _, reasons = node_check(row, pages, locators, plan)
        if i in decisions.HOLD_NODES and i not in decisions.VISUAL_NODE_NAMES:
            reasons.append(decisions.HOLD_NODES[i])
        name = row.get("name", row.get("text", ""))
        if name in decisions.EXTRA_HOLD_NAMES:
            reasons.append("ambiguous_ocr_identity_or_ontology_requires_review")
        if row["type"] in ["SampleQuestion", "Skill"]:
            reasons.append("question_or_skill_requires_separate_content_review")
        if row["type"] in ["Condition", "Finding", "Drug"] and re.search(
            r"^(?:C\.|Cl\.|M\.|Entero|Liên cầu)|toxin|Tetanoplasmin|Tetanolysin",
            name,
            re.IGNORECASE,
        ):
            reasons.append("microorganism_or_toxin_outside_current_patient_ontology")
        if row["type"] == "Condition" and re.search(
            r"^Tai nạn|^Chấn thương thể thao", name, re.IGNORECASE
        ):
            reasons.append("event_or_mechanism_not_diagnosis")
        if row["type"] == "Intervention" and re.fullmatch(
            r"(?:Đinh|Kim|Vít|Chỉ|Nẹp|Collar|Halo).*", name, re.IGNORECASE
        ):
            reasons.append("hardware_requires_explicit_procedure_mapping")
        if (
            row["type"] == "ClinicalPrinciple"
            and i != 2204
            and not re.search(r"nguyên tắc", name, re.IGNORECASE)
        ):
            reasons.append("principle_requires_explicit_normative_identity_review")
        if OCR_FLAGS.search(name):
            reasons.append("unresolved_ocr_in_identity")
        blocks = []
        for j, block in enumerate(row.get("content", [])):
            problems = sorted({r for s in block["sources"] for r in quote_flags(s)})
            block_audit.append(
                {
                    "node": f"N{i}",
                    "block": j,
                    "retained_in_candidate": not problems,
                    "reasons": problems,
                    "source_locator_ids": [s["locator_id"] for s in block["sources"]],
                }
            )
            if not problems:
                blocks.append(block)
        if row.get("content"):
            row["content"] = blocks
            if not blocks or all(len(c["text"].strip()) < 35 for c in blocks):
                reasons.append("no_substantive_content_after_source_quality_gate")
            elif norm(name) not in norm("\n".join(c["text"] for c in blocks)):
                reasons.append("identity_only_in_held_content")
        reasons = sorted(set(reasons))
        entry = {
            "ordinal": f"N{i}",
            "id": row["id"],
            "chapter": checks[i]["chapter"],
            "type": row["type"],
            "name": name,
            "decision": "hold" if reasons else "candidate",
            "reasons": reasons,
        }
        node_audit.append(entry)
        if not reasons:
            nodes[row["id"]] = row
    edge_audit, edges = [], []
    for i, original in enumerate(graph["edges"]):
        row = copy.deepcopy(original)
        reasons = []
        if i not in decisions.KEEP | decisions.REVERSE:
            reasons.append("no_explicit_supported_semantic_edge_approval")
        if i in decisions.REVERSE:
            row["from_id"], row["to_id"] = row["to_id"], row["from_id"]
        if i in decisions.CONDITIONS:
            row["condition"] = decisions.CONDITIONS[i]
        if row["from_id"] not in nodes or row["to_id"] not in nodes:
            reasons.append("endpoint_outside_approved_node_subset")
        reasons += sorted({r for s in row["sources"] for r in quote_flags(s)})
        if row.get("condition") and OCR_FLAGS.search(row["condition"]):
            reasons.append("ocr_or_incomplete_qualifier_in_condition")
        entry = {
            "ordinal": f"E{i}",
            "id": row["id"],
            "decision": "hold" if reasons else "candidate",
            "reasons": sorted(set(reasons)),
            "reversed": i in decisions.REVERSE,
            "condition_explicitly_reviewed": i in decisions.CONDITIONS,
            "before": original,
            "after": row if not reasons else None,
        }
        edge_audit.append(entry)
        if not reasons:
            edges.append(row)
    # A category's parent is established only by an approved, sourced HAS_CATEGORY.
    category_parents = {}
    for e in edges:
        if e["type"] == "HAS_CATEGORY":
            category_parents.setdefault(e["to_id"], set()).add(e["from_id"])
    for identifier, n in list(nodes.items()):
        if n["type"] != "ClassificationCategory":
            continue
        parents = category_parents.get(identifier, set())
        entry = next(r for r in node_audit if r["id"] == identifier)
        if len(parents) != 1:
            del nodes[identifier]
            entry["decision"] = "hold"
            entry["reasons"].append("category_parent_not_uniquely_source_approved")
        else:
            parent = nodes[next(iter(parents))]
            n["name"] = (
                f"{n['name']} — {parent['name']} (sách 2021, bài {entry['chapter']})"
            )
            entry["scoped_name"] = n["name"]
    edges = [e for e in edges if e["from_id"] in nodes and e["to_id"] in nodes]
    accepted_edges = {e["id"] for e in edges}
    for r in edge_audit:
        if r["id"] in accepted_edges:
            r["decision"] = "include"
        elif r["decision"] == "candidate":
            r["decision"] = "hold"
            r["reasons"].append("category_scope_unresolved")
            r["after"] = None
    # Do not silently merge concepts by name across chapters or with the 2006 book.
    for r in node_audit:
        if r["id"] in nodes:
            r["decision"] = "include"
    for r in block_audit:
        r["included_in_graph"] = (
            r["retained_in_candidate"]
            and graph["nodes"][int(r["node"][1:])]["id"] in nodes
        )
    result = {
        "schema_version": graph["schema_version"],
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    dry_run_loader(result)
    combined = OUT / "combined"
    combined.mkdir(parents=True, exist_ok=True)
    target = combined / "graph.json"
    imported = OUT / "imports/apply/import-manifest.json"
    if imported.exists() and fingerprint(read_json(target)) != fingerprint(result):
        raise ValueError("cannot_replace_graph_after_import")
    write_json(target, result)
    used = {
        s["locator_id"] for row in result["nodes"] + result["edges"] for s in refs(row)
    }
    used_pages = {locators[k]["pdf_page"] for k in used}
    jsonl(combined / "audit/pages.jsonl", [pages[k] for k in sorted(used_pages)])
    write_json(combined / "audit/locators.json", [locators[k] for k in sorted(used)])
    count = validate_locators(result, combined)
    jsonl(OUT / "audit/node-decisions.jsonl", node_audit)
    jsonl(OUT / "audit/content-block-decisions.jsonl", block_audit)
    jsonl(OUT / "audit/edge-decisions.jsonl", edge_audit)
    original = read_json(SOURCE / "graph.json")
    held_node_ids = {r["id"] for r in node_audit if r["decision"] == "hold"}
    write_json(
        OUT / "pending-graph.json",
        {
            "status": "not_imported_requires_review",
            "nodes": [n for n in original["nodes"] if n["id"] in held_node_ids],
            "edges": [e for e in original["edges"] if e["id"] not in accepted_edges],
            "note": "Original proposals: edges can reference included nodes in combined/graph.json. Not an importable bundle.",
        },
    )
    groups = {}
    for n in result["nodes"]:
        groups.setdefault((n["type"], norm(n["name"])), []).append(n["id"])
    write_json(
        OUT / "audit/equivalence-candidates.json",
        {
            "status": "not_merged_by_name",
            "within_2021_candidates": [
                {"type": k[0], "normalized_name": k[1], "ids": v}
                for k, v in groups.items()
                if len(v) > 1
            ],
            "cross_book_canonical_merge_status": "not_authorized_by_source_equivalence_in_this_pass",
            "canonical_registry_unchanged": True,
        },
    )
    write_json(
        OUT / "audit/review-method.json",
        {
            "all_chapters_examined": sorted(decisions.REVIEWED_CHAPTERS),
            "pdf_images_actually_viewed": sorted(decisions.PDF_VIEWED),
            "all_records_exact_ocr_and_raw_offsets_checked": True,
            "semantic_edge_approvals_are_explicit": True,
            "all_pdf_pages_manually_read": False,
            "expert_verified": False,
            "cross_book_name_only_merges": 0,
            "new_llm_calls": 0,
            "quantitative_pattern_matches_without_image_review_held": True,
            "original_locators_checked": original_locators_checked,
            "unverified_doses_held": True,
        },
    )
    chapters = []
    for c in plan["chapters"]:
        number = c["lesson_number"]
        folder = OUT / f"chapters/2021-bai-{number:02d}"
        ids = {r["id"] for r in node_audit if r["chapter"] == number}
        chapter_nodes = [n for n in result["nodes"] if n["id"] in ids]
        chapter_edges = [e for e in edges if e["from_id"] in ids or e["to_id"] in ids]
        chapters.append(
            {
                "lesson_number": number,
                "title": c["title"],
                "nodes": len(chapter_nodes),
                "edges": len(chapter_edges),
                "draft_nodes": len(ids),
            }
        )
        write_json(
            folder / "reviewed-graph.json",
            {
                "schema_version": graph["schema_version"],
                "nodes": chapter_nodes,
                "edges": chapter_edges,
            },
        )
    summary = {
        "draft_nodes": len(graph["nodes"]),
        "draft_edges": len(graph["edges"]),
        "included_nodes": len(nodes),
        "included_edges": len(edges),
        "held_nodes": len(graph["nodes"]) - len(nodes),
        "held_edges": len(graph["edges"]) - len(edges),
        "content_blocks_total": len(block_audit),
        "content_blocks_held_before_node_gate": sum(
            not r["retained_in_candidate"] for r in block_audit
        ),
        "content_blocks_included": sum(r["included_in_graph"] for r in block_audit),
        "visual_patches": len(read_json(OUT / "audit/visual-ocr-patches.json")),
        "reversed_edges_importable": sum(
            r["reversed"] and r["decision"] == "include" for r in edge_audit
        ),
        "condition_changes_importable": sum(
            r["condition_explicitly_reviewed"] and r["decision"] == "include"
            for r in edge_audit
        ),
        "locators_checked": count,
        "chapters": chapters,
        "node_types": dict(Counter(n["type"] for n in nodes.values())),
        "edge_types": dict(Counter(e["type"] for e in edges)),
    }
    write_json(OUT / "review-summary.json", summary)
    build_html(result, summary, node_audit, edge_audit)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "chapters"}, ensure_ascii=True
        )
    )


def build_html(graph, summary, node_audit, edge_audit):
    esc = lambda s: html.escape(str(s))
    by_id = {n["id"]: n for n in graph["nodes"]}
    node_sections = []
    for n in graph["nodes"]:
        item = next(r for r in node_audit if r["id"] == n["id"])
        blocks = []
        for c in n.get("content", []):
            sources = ", ".join(
                "PDF " + ",".join(map(str, s["pdf_pages"])) + " / " + s["locator_id"]
                for s in c["sources"]
            )
            blocks.append(f"<pre>{esc(c['text'])}</pre><small>{esc(sources)}</small>")
        related = []
        for e in graph["edges"]:
            if n["id"] in [e["from_id"], e["to_id"]]:
                left, right = by_id[e["from_id"]]["name"], by_id[e["to_id"]]["name"]
                related.append(
                    f"<li>{esc(left)} → <b>{esc(e['type'])}</b> → {esc(right)}<br>{esc(e['condition'] or '')}<details><summary>Nguồn quan hệ</summary><pre>{esc(chr(10).join(s['excerpt'] for s in e['sources']))}</pre></details></li>"
                )
        node_sections.append(
            f'<details class="node" data-chapter="{item["chapter"]}"><summary>Bài {item["chapter"]} · {esc(n["type"])} · {esc(n["name"])}</summary><code>{esc(n["id"])}</code>{"".join(blocks)}<ul>{"".join(related)}</ul></details>'
        )
    pending_nodes = [r for r in node_audit if r["decision"] == "hold"]
    pending_edges = [r for r in edge_audit if r["decision"] == "hold"]
    table = "".join(
        f"<tr><td>{c['lesson_number']}</td><td>{esc(c['title'])}</td><td>{c['nodes']}/{c['draft_nodes']}</td><td>{c['edges']}</td></tr>"
        for c in summary["chapters"]
    )
    document = f"""<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đối chiếu sách ngoại khoa 2021</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:32px auto;padding:0 20px;background:#f7f8fc;color:#152132}}details{{background:white;border:1px solid #cad2de;padding:12px;margin:9px 0}}summary{{cursor:pointer;font-weight:600}}pre{{white-space:pre-wrap;line-height:1.55}}small,code{{color:#46566b}}input{{padding:12px;width:95%;position:sticky;top:0}}td,th{{padding:7px;border-bottom:1px solid #ddd;text-align:left}}table{{width:100%}}</style>
<h1>Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021)</h1>
<p>{summary["included_nodes"]} node, {summary["included_edges"]} quan hệ trong phần đủ điều kiện nhập. Đã rà soát nguồn OCR, định danh/loại node và bằng chứng quan hệ; không phải xác nhận chuyên môn y khoa.</p>
<p>Chỉ nhập các đoạn nguồn đạt điều kiện. Có {len(pending_nodes)} node và {len(pending_edges)} quan hệ giữ ngoài graph; còn 19 cửa sổ trích xuất lỗi. Không được hiểu đây là toàn bộ nội dung cuốn sách.</p>
<p><a href="combined/graph.json">JSON đã chuẩn bị nhập</a> · <a href="audit/node-decisions.jsonl">Quyết định từng node</a> · <a href="audit/content-block-decisions.jsonl">Quyết định từng đoạn nội dung</a> · <a href="audit/edge-decisions.jsonl">Quyết định từng quan hệ</a> · <a href="missing-extraction.json">Phần chưa trích xuất</a> · <a href="report.md">Báo cáo</a></p>
<details><summary>Thống kê 36 bài</summary><table><tr><th>Bài</th><th>Tên</th><th>Node đạt/nháp</th><th>Quan hệ đạt</th></tr>{table}</table></details>
<input id="q" placeholder="Tìm tên, nội dung, mã node hoặc bài…" aria-label="Tìm nội dung">
{"".join(node_sections)}
<script>document.querySelector('#q').addEventListener('input',e=>{{const q=e.target.value.toLocaleLowerCase();document.querySelectorAll('.node').forEach(n=>n.hidden=!n.textContent.toLocaleLowerCase().includes(q));}});</script></html>"""
    (OUT / "review.html").write_text(document, encoding="utf-8")


def verify_baseline(before, after):
    """All pre-existing identities, labels, endpoints and properties stay intact."""
    actual_nodes = {r["element_id"]: r for r in after["nodes"]}
    actual_edges = {r["element_id"]: r for r in after["relationships"]}
    for row in before["nodes"]:
        actual = actual_nodes.get(row["element_id"])
        if (
            not actual
            or actual["properties"] != row["properties"]
            or set(actual["labels"]) != set(row["labels"])
        ):
            raise ValueError("preexisting_node_changed")
    for row in before["relationships"]:
        if actual_edges.get(row["element_id"]) != row:
            raise ValueError("preexisting_relationship_changed")


def apply_reviewed():
    assert_protected()
    graph_file = OUT / "combined/graph.json"
    graph = read_json(graph_file)
    folder = OUT / "imports"
    before = read_json(OUT / "audit/neo4j-before-all.json")
    for phase, apply in [("preflight", False), ("apply", True), ("idempotency", False)]:
        path = folder / phase / "import-manifest.json"
        if path.exists():
            manifest = read_json(path)
            expected = "imported_and_verified" if apply else "preflight_passed"
            if manifest["status"] != expected or manifest[
                "graph_sha256"
            ] != fingerprint(graph):
                raise ValueError(
                    "existing_import_audit_requires_diagnosis_no_automatic_retry"
                )
        else:
            if phase == "apply":
                preflight = read_json(folder / "preflight/import-plan.json")
                if any(
                    r["action"] != "create"
                    for key in ["nodes", "edges"]
                    for r in preflight[key]
                ):
                    raise ValueError("new_book_must_not_update_existing_identities")
                verify_baseline(before, read_json(folder / "preflight/before-all.json"))
            manifest = import_review(
                graph_file, folder / phase, env_file=ROOT / ".env", apply=apply
            )
        if phase == "idempotency" and any(
            action != "skip"
            for counts in manifest["counts"].values()
            for action in counts
        ):
            raise ValueError("idempotency_check_failed")
        print(
            json.dumps(
                {
                    "phase": phase,
                    "status": manifest["status"],
                    "counts": manifest["counts"],
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
    finalize()


def finalize():
    from dotenv import dotenv_values
    from neo4j import GraphDatabase

    from knowledge_pipeline.neo4j_export import read_graph

    manifest = read_json(OUT / "imports/apply/import-manifest.json")
    if manifest["status"] != "imported_and_verified":
        raise ValueError("no_verified_import")
    values = dotenv_values(ROOT / ".env", interpolate=False)
    with (
        GraphDatabase.driver(
            values["NEO4J_URI"],
            auth=(values["NEO4J_USERNAME"], values["NEO4J_PASSWORD"]),
            connection_timeout=5,
            connection_acquisition_timeout=10,
            max_transaction_retry_time=0,
        ) as driver,
        driver.session(database=values["NEO4J_DATABASE"]) as session,
        session.begin_transaction(timeout=30) as tx,
    ):
        after = read_graph(tx, None)
    before = read_json(OUT / "audit/neo4j-before-all.json")
    verify_baseline(before, after)
    graph = read_json(OUT / "combined/graph.json")
    actual_nodes = {r["properties"].get("id"): r for r in after["nodes"]}
    actual_edges = {r["properties"].get("id"): r for r in after["relationships"]}
    payload = dry_run_loader(graph)
    elements = {r["element_id"]: r["properties"].get("id") for r in after["nodes"]}
    for row in payload["nodes"]:
        found = actual_nodes[row["properties"]["id"]]
        if not set(row["labels"]) <= set(found["labels"]) or any(
            found["properties"].get(k) != v for k, v in row["properties"].items()
        ):
            raise ValueError("final_node_readback_mismatch")
    for row in payload["edges"]:
        found = actual_edges[row["properties"]["id"]]
        if (
            elements[found["start_node"]],
            found["type"],
            elements[found["end_node"]],
        ) != (row["from_id"], row["type"], row["to_id"]) or any(
            found["properties"].get(k) != v for k, v in row["properties"].items()
        ):
            raise ValueError("final_relationship_readback_mismatch")
    if len(after["nodes"]) != len(before["nodes"]) + len(graph["nodes"]) or len(
        after["relationships"]
    ) != len(before["relationships"]) + len(graph["edges"]):
        raise ValueError("unexpected_total_database_counts")
    protected = assert_protected()
    write_json(OUT / "audit/neo4j-after-all.json", after)
    verification = {
        "status": "imported_and_verified",
        "prior_nodes_unchanged": len(before["nodes"]),
        "prior_edges_unchanged": len(before["relationships"]),
        "new_nodes_read_back": len(graph["nodes"]),
        "new_edges_read_back": len(graph["edges"]),
        "total_nodes": len(after["nodes"]),
        "total_edges": len(after["relationships"]),
        "protected_source_files_unchanged": protected,
        "idempotent": True,
        "expert_verified": False,
        "new_llm_calls": 0,
    }
    write_json(OUT / "audit/final-database-verification.json", verification)
    report(read_json(OUT / "review-summary.json"), verification)
    print(json.dumps(verification, ensure_ascii=True), flush=True)


def report(summary, verification):
    method = read_json(OUT / "audit/review-method.json")
    gaps = read_json(OUT / "missing-extraction.json")
    rows = [
        f"| {c['lesson_number']} | {c['title']} | {c['nodes']} / {c['draft_nodes']} | {c['edges']} |"
        for c in summary["chapters"]
    ]
    text = f"""# Đối chiếu và import sách ngoại khoa 2021

Nguồn: **Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021)**, `SRC_ORTHO_TEXTBOOK_001`, PDF `data/raw-source/DVC.005844.pdf`, OCR `data/graduate/DVC.005844.json`.

Đã import và đọc lại xác nhận **{summary["included_nodes"]} node / {summary["included_edges"]} quan hệ**, có nội dung từ cả 36 bài. Đây là phần đạt điều kiện của bản nháp, **chưa phải toàn bộ sách đã hoàn thiện**.

## Phạm vi kiểm tra

- Kiểm tra tự động toàn bộ {summary["draft_nodes"]} node và {summary["draft_edges"]} quan hệ: trích dẫn khớp OCR, trang nguồn, vị trí văn bản đã sửa và vị trí văn bản OCR gốc. Không xem đúng JSON là đủ bằng chứng y khoa.
- Đọc danh sách loại/tên của các node qua cửa kiểm tra ban đầu; xét bằng chứng của 657 quan hệ có hai đầu qua cửa này trong hồ sơ 36 bài. Quan hệ thiếu bằng chứng, đảo nghĩa, nhầm chẩn đoán phân biệt/chống chỉ định hoặc không rõ điều kiện được giữ ngoài graph. Sửa chiều {summary["reversed_edges_importable"]} quan hệ được nhập; bổ sung/làm rõ điều kiện cho {summary["condition_changes_importable"]} quan hệ được nhập.
- Đã xem ảnh PDF ở {len(method["pdf_images_actually_viewed"])} trang: {", ".join(map(str, method["pdf_images_actually_viewed"]))}. Có {summary["visual_patches"]} thay thế OCR cụ thể theo trang, giữ dấu vết về OCR gốc và ảnh bằng chứng. Không thay đổi số liệu hay phủ định bằng suy đoán.
- Lọc riêng các đoạn có lỗi OCR ảnh hưởng ý nghĩa, liều/thể tích chưa xác minh và các mẫu số liệu chưa kiểm tra ảnh. Chỉ {summary["content_blocks_included"]} / {summary["content_blocks_total"]} đoạn nội dung nháp được giữ trong bản nhập; một node có thể chỉ chứa một phần nội dung đạt. Chi tiết từng đoạn ở `audit/content-block-decisions.jsonl`.
- Câu hỏi, đáp án, kỹ năng và các định danh/kiểu node còn mơ hồ được giữ để duyệt tiếp. Không suy đáp án; không ép dụng cụ hoặc vi khuẩn thành thuốc/bệnh.
- Kiểm tra schema, loại hai đầu quan hệ, mã duy nhất, node bị thiếu, chu trình phân cấp, khả năng mã hóa/đọc lại JSON. Các hạng phân loại được đặt trong phạm vi cha có nguồn.
- Không đọc thủ công mọi trang PDF và mọi đoạn OCR; **không xác nhận chuyên môn y khoa**. Kiểm tra nguồn là kiểm tra trung thành với sách, không đánh giá đây là hướng dẫn điều trị hiện hành.

## Phần còn lại

- **{summary["held_nodes"]} node và {summary["held_edges"]} quan hệ nháp** chưa nhập, kèm lý do trong các file quyết định. Có cả bản ghi có thể đúng nhưng chưa đủ bằng chứng/nguồn rõ để chấp nhận trong lần này.
- 19 cửa sổ LLM không có kết quả; 255 cửa sổ có kết quả một phần theo schema. Không gọi lại LLM trong lần đối chiếu này.
- Thiếu phần mở đầu nguồn của các bài 10, 14, 16, 18. Không dùng mục lục để tự bổ sung nội dung y khoa.
- 13.626 đề xuất `review-items` và 875 đề xuất `rejected-items` của đợt trích xuất gốc vẫn ngoài graph; đường dẫn được giữ trong `audit/original-held-index.json`. Đây là số đề xuất thô, không phải số khái niệm duy nhất.
- Chưa gộp canonical giữa các chương/sách theo tên. Giữ ID và nguồn riêng; các tên tương đồng được đưa vào `audit/equivalence-candidates.json`, registry canonical không thay đổi.

## Neo4j

- Đã chạy preflight trước khi ghi, import trong một giao dịch có kiểm tra và đọc lại sau commit. Chạy preflight lần hai: toàn bộ `skip`, không tạo trùng.
- Toàn bộ **{verification["prior_nodes_unchanged"]} node / {verification["prior_edges_unchanged"]} quan hệ cũ** giữ nguyên nhãn, thuộc tính và hai đầu.
- Hiện DB có **{verification["total_nodes"]} node / {verification["total_edges"]} quan hệ**.
- Đối chiếu hash {verification["protected_source_files_unchanged"]} file được bảo vệ: PDF, OCR, đầu ra LLM, kế hoạch, pipeline, registry và graph cấp cứu cũ giữ nguyên.
- Không xóa dữ liệu, không sửa PostgreSQL, cấu hình mạng, VPN hay `.env`; không phát sinh cuộc gọi LLM.

## File xem và kiểm tra

- `review.html`: tra cứu nội dung thực sự có trong bản nhập và nguồn của từng quan hệ.
- `combined/graph.json`: đầy đủ node/quan hệ được nhập trong lần này.
- `pending-graph.json`: bản nháp gốc chưa nhập; không phải bundle có thể import trực tiếp.
- `audit/node-decisions.jsonl`, `audit/content-block-decisions.jsonl`, `audit/edge-decisions.jsonl`: quyết định có thể kiểm tra lại.
- `audit/visual-ocr-patches.json`: trước/sau từng sửa OCR cùng ảnh bằng chứng; dữ liệu OCR gốc không bị ghi đè.
- `imports/preflight`, `imports/apply`, `imports/idempotency`: kế hoạch, snapshot và kết quả.
- `audit/final-database-verification.json`: xác nhận cuối cùng sau đọc lại DB.
- `missing-extraction.json`: danh sách cửa sổ lỗi và phần nguồn thiếu ({len(gaps["source_gaps"])} mục).

Xem nhanh sách 2021 trong Neo4j Browser:

```cypher
MATCH (n)
WHERE n.content CONTAINS 'SRC_ORTHO_TEXTBOOK_001'
OPTIONAL MATCH (n)-[r]-(m)
RETURN n, r, m LIMIT 100;
```

## Theo bài

| Bài | Tên | Node nhập / nháp | Quan hệ nhập |
| --- | --- | ---: | ---: |
{chr(10).join(rows)}
"""
    (OUT / "report.md").write_text(text, encoding="utf-8")
    page = OUT / "review.html"
    document = page.read_text(encoding="utf-8")
    banner = f'<p id="database-verification"><b>Đã import và đọc lại Neo4j:</b> {verification["new_nodes_read_back"]} node, {verification["new_edges_read_back"]} quan hệ mới. Dữ liệu cũ giữ nguyên. <a href="audit/final-database-verification.json">Bằng chứng</a>.</p>'
    document = re.sub(r'<p id="database-verification">.*?</p>', "", document)
    page.write_text(
        document.replace('<input id="q"', banner + '<input id="q"'), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--render", type=int, nargs="+")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--apply-reviewed", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.render:
        render(args.render)
    if args.compile:
        compile_review()
    if args.apply_reviewed:
        apply_reviewed()
    if args.verify:
        finalize()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- never print driver credentials
        error = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
        }
        if isinstance(exc, ValueError) and re.fullmatch(r"[A-Za-z_]+", str(exc)):
            error["reason"] = str(exc)
        print(json.dumps(error, ensure_ascii=True))
        raise SystemExit(1) from None
