"""Source-grounded draft policy and human review exports; no medical auto-approval."""

import html
import re
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.pipeline import jsonl
from knowledge_pipeline.validation import normalized

from .contracts import MEDICAL, RELATIONS
from .loader import dry_run_loader
from .registry import resolve_graph
from .validation import check_edge, cycle_if_added, source_entries, supported_node


class ReviewOnly(ValueError):
    """A sourced proposal remains in the review queue, outside the valid graph."""


def whole_sources(refs, blocks, changes):
    result = []
    for ref in refs:
        if ref["block_id"] not in blocks:
            raise ValueError("unknown_block")
        # First validate the original citation: expansion cannot rescue invented quotes.
        source_entries([ref], blocks, {})
        if "excerpt" in ref and normalized(ref["excerpt"]) != normalized(
            blocks[ref["block_id"]]["text"]
        ):
            changes.append({"reason": "restored_whole_cited_block", "original": ref})
        value = {"block_id": ref["block_id"]}
        if value not in result:
            result.append(value)
    return result


def draft_node(raw, blocks, locators):
    row, changes = deepcopy(raw), []
    kind = row["type"]
    if kind == "SampleQuestion":
        row["sources"] = whole_sources(row["sources"], blocks, changes)
        if any(blocks[r["block_id"]]["role"] != "question" for r in row["sources"]):
            raise ReviewOnly("question_not_in_question_source")
        exact = "\n".join(blocks[r["block_id"]]["text"] for r in row["sources"])
        if normalized(exact) != normalized(row["text"]):
            changes.append(
                {
                    "reason": "restored_question_from_cited_source",
                    "original_text": row["text"],
                }
            )
        row["text"] = exact
        options = re.findall(r"(?m)^\s*[A-Za-z][.)]\s+(.+)$", exact)
        if row["options"] != options:
            changes.append(
                {
                    "reason": "restored_source_options",
                    "original_options": row["options"],
                }
            )
            row["options"] = options
        if options and row["format"] != "multiple_choice":
            changes.append({"reason": "source_options_need_format_review"})
        try:
            source_entries(row["answer_sources"], blocks, locators)
        except ValueError:
            changes.append(
                {
                    "reason": "removed_unsupported_answer_source",
                    "original_answer_sources": row["answer_sources"],
                }
            )
            row.update(answer=None, explanation=None, answer_sources=[])
        try:
            node, key = supported_node(row, blocks, locators)
        except ValueError as exc:
            if str(exc) not in {
                "invented_answer",
                "answer_without_book_answer",
                "invented_answer_or_explanation",
            }:
                raise
            changes.append(
                {
                    "reason": "removed_unsupported_answer",
                    "original_answer": row["answer"],
                    "original_explanation": row["explanation"],
                }
            )
            row.update(answer=None, explanation=None, answer_sources=[])
            node, key = supported_node(row, blocks, locators)
        return node, key, changes

    identity = source_entries(row["identity_sources"], blocks, locators)
    identity_text = "\n".join(s["excerpt"] for s in identity)
    if kind in MEDICAL:
        kept = []
        for alias in row["aliases"]:
            if normalized(alias).casefold() in normalized(
                identity_text
            ).casefold() and re.search(
                r"còn gọi|hay gọi|tên khác|also called|known as",
                identity_text,
                re.IGNORECASE,
            ):
                kept.append(alias)
            else:
                changes.append({"reason": "removed_unsupported_alias", "alias": alias})
        row["aliases"] = kept
    else:
        source_entries(row["basis_sources"], blocks, locators)
        expected = {
            "learning_objective": {"learning_objective"},
            "practice_requirement": {"practice_requirement"},
            "procedural_instruction": {"procedure"},
        }[row["basis"]]
        if any(
            blocks[s["block_id"]]["role"] not in expected for s in row["basis_sources"]
        ):
            raise ReviewOnly("skill_basis_scope_requires_review")

    for content in row["content"]:
        content["sources"] = whole_sources(content["sources"], blocks, changes)
    try:
        node, key = supported_node(row, blocks, locators)
    except ValueError as exc:
        reason = str(exc)
        if reason not in {
            "name_not_supported",
            "title_only_content_is_not_medical_description",
            "skill_name_needs_action_and_object",
            "skill_action_not_in_objective",
            "theory_does_not_prove_practical_skill",
        }:
            raise
        changes.append(
            {"reason": reason, "decision": "retain_sourced_proposal_for_review"}
        )
        content = []
        for c in row["content"]:
            ss = source_entries(
                c["sources"], blocks, locators, preserve_qualifiers=True
            )
            content.append({"text": "\n".join(s["excerpt"] for s in ss), "sources": ss})
        key = fingerprint(
            [
                kind,
                normalized(row["name"]).casefold(),
                row.get("kind"),
                sorted(
                    (s["source_id"], s["locator_id"], normalized(s["excerpt"]))
                    for s in identity
                ),
            ]
        )
        node = {
            k: v
            for k, v in row.items()
            if k
            not in {"identity_sources", "local_id", "basis", "basis_sources", "content"}
        }
        node.update(id="CAND2_" + key[:24], content=content)
    for c in node["content"]:
        if len(c["text"].split()) < 6:
            changes.append({"reason": "thin_content_needs_review"})
    return node, key, changes


def draft_edge(raw, nodes, blocks, locators):
    if raw["from_id"] not in nodes or raw["to_id"] not in nodes:
        raise ReviewOnly("endpoint_not_in_draft_graph")
    left, right = nodes[raw["from_id"]], nodes[raw["to_id"]]
    if raw["type"] not in RELATIONS:
        raise ValueError("unsupported_relation")
    domain, range_ = RELATIONS[raw["type"]]
    if left["type"] not in domain or right["type"] not in range_:
        raise ReviewOnly("invalid_relationship_end_types_no_auto_reversal")
    if raw["type"] == "IS_A" and left["type"] != right["type"]:
        raise ReviewOnly("incompatible_is_a_types")
    changes = []
    # Qualifiers, exceptions and neighboring sentences in this block stay as source text.
    row = {**deepcopy(raw), "sources": whole_sources(raw["sources"], blocks, changes)}
    ss = source_entries(row["sources"], blocks, locators)
    text = "\n".join(s["excerpt"] for s in ss)
    if row["condition"] is not None and (
        not row["condition"].strip()
        or normalized(row["condition"]) not in normalized(text)
    ):
        raise ReviewOnly("condition_not_in_source")
    try:
        edge = check_edge(row, nodes, blocks, locators)
    except ValueError as exc:
        changes.append(
            {"reason": str(exc), "decision": "retain_unverified_sourced_relationship"}
        )
        edge = {
            "from_id": left["id"],
            "to_id": right["id"],
            "type": row["type"],
            "condition": row["condition"],
            "sources": ss,
        }
        edge["id"] = "KG2E_" + fingerprint(edge)[:24]
    return edge, changes


def resolve_draft(candidates, canonical_registry, draft_registry_path):
    """Stable allocation is separate from reviewed equivalence; no name-based merge."""
    path = Path(draft_registry_path)
    registry = (
        read_json(path)
        if path.exists()
        else {"version": "draft-ids-v1", "bindings": {}}
    )
    canonical, resolution = resolve_graph(candidates, canonical_registry)
    mapping = dict(resolution["candidate_to_canonical"])
    nodes = {n["id"]: deepcopy(n) for n in canonical["nodes"]}
    pending, migrations = [], []
    for candidate in candidates["nodes"]:
        key = candidate["id"]
        identifier = (
            mapping.get(key)
            or registry["bindings"].get(key)
            or "DRN_" + uuid5(NAMESPACE_URL, "medresident/kg-v2/" + key).hex
        )
        previous = registry["bindings"].get(key)
        if previous and previous != identifier:
            migrations.append(
                {
                    "old_id": previous,
                    "new_id": identifier,
                    "candidate_id": key,
                    "basis": "confirmed_canonical_binding",
                }
            )
        registry["bindings"][key] = identifier
        mapping[key] = identifier
        if identifier not in nodes:
            nodes[identifier] = {**deepcopy(candidate), "id": identifier}
        if key not in resolution["candidate_to_canonical"]:
            pending.append(
                {
                    "reason": "draft_identity_not_equivalence_approved",
                    "candidate_id": key,
                    "record_id": identifier,
                }
            )
    edges, held, edge_mapping = {}, [], {}
    for edge in candidates["edges"]:
        value = {
            **deepcopy(edge),
            "from_id": mapping[edge["from_id"]],
            "to_id": mapping[edge["to_id"]],
        }
        value.pop("id")
        value["id"] = "DRE_" + fingerprint(value)[:24]
        if cycle_if_added(edges.values(), value):
            held.append({"reason": "hierarchy_cycle_after_remap", "original": edge})
        else:
            edges[value["id"]] = value
            edge_mapping[edge["id"]] = value["id"]
    graph = {
        "schema_version": candidates["schema_version"],
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges.values(), key=lambda e: e["id"]),
    }
    dry_run_loader(graph)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One sequential writer; atomic replacement prevents a half-written mapping.
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_json(temporary, registry)
    temporary.replace(path)
    return graph, {
        "draft_id_mapping": mapping,
        "draft_identity_pending": pending,
        "draft_id_migrations": migrations,
        "draft_remap_held": held,
        "draft_edge_id_mapping": edge_mapping,
    }


def write_review_output(output, graph, audit, windows, catalog, report):
    def proposal_refs(value):
        # Held proposals intentionally do NOT satisfy the extraction schema.
        # Read references defensively for display only; never repair the graph
        # or mutate the original rejected JSON in the audit.
        if not isinstance(value, dict):
            return []

        def refs(field):
            if isinstance(field, dict):
                field = [field]
            if not isinstance(field, list):
                return []
            return [
                ref
                for ref in field
                if isinstance(ref, dict) and isinstance(ref.get("block_id"), str)
            ]

        result = []
        for key in ("sources", "identity_sources", "basis_sources"):
            result.extend(refs(value.get(key)))
        contents = value.get("content")
        if isinstance(contents, list):
            for content in contents:
                if isinstance(content, dict):
                    result.extend(refs(content.get("sources")))
        return result

    output = Path(output)
    mapping = audit.get("draft_id_mapping", {})
    reviews = (
        list(audit.get("review_items", []))
        + list(audit.get("draft_identity_pending", []))
        + list(audit.get("draft_remap_held", []))
    )
    for rejected in audit.get("rejected", []):
        if "ocr" in rejected["reason"]:
            reviews.append(
                {
                    **rejected,
                    "reason": rejected["reason"],
                    "decision": "source_outside_graph",
                }
            )
    for row in audit.get("merge_proposals", []):
        reviews.append({**row, "reason": "possible_duplicate_no_auto_merge"})
    covered = {
        s["locator_id"]
        for n in graph["nodes"]
        for s in (
            n.get("sources", [])
            + [s for c in n.get("content", []) for s in c["sources"]]
        )
    }
    locators = {s["locator_id"]: s for s in audit.get("locators", [])}
    covered_blocks = {locators[k]["block_id"] for k in covered if k in locators}
    seen = set()
    for w in windows:
        for block in w["blocks"]:
            key = block["block_id"]
            if key in seen:
                continue
            seen.add(key)
            if key not in covered_blocks and (
                block.get("kind") == "body" or re.search(r":\s*\S.{12,}", block["text"])
            ):
                reviews.append(
                    {
                        "reason": "source_block_not_retained_reextract_queue",
                        "window_id": w["window_id"],
                        "block_id": key,
                        "source_id": block["source_id"],
                        "pdf_page": block["pdf_page"],
                        "excerpt": block["text"],
                    }
                )
    unique = {}
    block_lookup = {b["block_id"]: b for w in windows for b in w["blocks"]}
    for row in reviews:
        row = deepcopy(row)
        original = row.get("candidate", row.get("original", {}))
        refs = proposal_refs(original)
        if row.get("block_id"):
            refs.append({"block_id": row["block_id"]})
        contexts = {}
        for ref in refs:
            block = block_lookup.get(ref["block_id"])
            if block:
                contexts[block["block_id"]] = {
                    "source_id": block["source_id"],
                    "pdf_pages": [block["pdf_page"]],
                    "printed_pages": [block["printed_page_label"]]
                    if block.get("printed_page_label")
                    else [],
                    "excerpt": block["text"],
                    "block_id": block["block_id"],
                }
        if contexts:
            row["source_contexts"] = list(contexts.values())
        if row.get("candidate_id") in mapping:
            row["record_id"] = mapping[row["candidate_id"]]
        if row.get("edge_id") in audit.get("draft_edge_id_mapping", {}):
            row["record_id"] = audit["draft_edge_id_mapping"][row["edge_id"]]
        row["review_id"] = "REV_" + fingerprint(row)[:20]
        unique[row["review_id"]] = row
    reviews = sorted(unique.values(), key=lambda r: r["review_id"])
    for name, rows in (
        ("draft-nodes", graph["nodes"]),
        ("draft-edges", graph["edges"]),
        ("review-items", reviews),
        ("rejected-items", audit.get("rejected", [])),
    ):
        jsonl(output / (name + ".jsonl"), rows)
    report.update(
        draft_nodes=len(graph["nodes"]),
        draft_edges=len(graph["edges"]),
        review_items=len(reviews),
        rejected_items=len(audit.get("rejected", [])),
        draft_only=True,
        neo4j_imported=False,
    )
    write_json(output / "audit/draft-id-mapping.json", mapping)
    write_json(output / "audit/loader-preview.json", dry_run_loader(graph))
    titles = {b["source_id"]: b.get("title", b["source_id"]) for b in catalog}
    sections = {}
    for w in windows:
        for b in w["blocks"]:
            sections.setdefault(b["block_id"], b.get("section_title", ""))
    node_by_id = {n["id"]: n for n in graph["nodes"]}
    esc = lambda value: html.escape(str(value))

    def source_html(ss):
        return "".join(
            "<details><summary>"
            + esc(titles.get(s["source_id"], s["source_id"]))
            + " · PDF "
            + esc(s["pdf_pages"])
            + " · trang in "
            + esc(s["printed_pages"])
            + "</summary><blockquote>"
            + esc(s["excerpt"])
            + "</blockquote><small>"
            + esc(s.get("locator_id", s.get("block_id", "")))
            + "</small></details>"
            for s in ss
        )

    friendly = {
        "removed_unsupported_alias": "Đã bỏ alias chưa có căn cứ; node vẫn được giữ",
        "restored_whole_cited_block": "Đã giữ nguyên cả block được trích để không mất điều kiện hoặc câu theo dõi",
        "draft_identity_not_equivalence_approved": "ID bản nháp ổn định; chưa xác nhận trùng nghĩa",
        "source_block_not_retained_reextract_queue": "Đoạn nguồn chưa được giữ: cần review hoặc trích bổ sung",
        "invalid_relationship_end_types_no_auto_reversal": "Đề xuất cạnh sai loại/hướng; giữ ngoài graph, không tự đảo chiều",
        "endpoint_not_in_draft_graph": "Cạnh có đầu mút chưa được giữ; cần đối chiếu đề xuất gốc",
        "unresolved_ocr_affects_meaning": "OCR/cấu trúc nguồn chưa rõ nghĩa; giữ ngoài graph",
        "skill_basis_scope_requires_review": "Chưa có căn cứ rõ cho năng lực được đề xuất",
        "possible_duplicate_no_auto_merge": "Có thể trùng khái niệm; chưa tự gộp",
        "negative_edge_requires_manual_review": "Cạnh cần đối chiếu phủ định trong nguồn",
        "window_failed_reextract_queue": "Cửa sổ chưa có kết quả do lỗi dịch vụ hoặc hết ngân sách",
    }

    def reason_text(row):
        return friendly.get(row["reason"], "Cần đối chiếu: " + row["reason"])

    body = [
        "<h1>Bản nháp KG để đối chiếu nguồn</h1><p>Nội dung chưa được duyệt. ID giúp chỉ rõ bản ghi cần sửa; việc cấp ID không xác nhận equivalence.</p>"
    ]
    for sid in sorted(
        {
            s["source_id"]
            for n in graph["nodes"]
            for s in n.get("sources", [])
            + [s for c in n.get("content", []) for s in c["sources"]]
        }
    ):
        body.append("<h2>" + esc(titles.get(sid, sid)) + "</h2>")

        def section_for(n, source_id=sid):
            ss = n.get("sources", []) + [
                s for c in n.get("content", []) for s in c["sources"]
            ]
            return next(
                (
                    sections.get(locators[s["locator_id"]]["block_id"], "")
                    for s in ss
                    if s["source_id"] == source_id and s["locator_id"] in locators
                ),
                "",
            )

        previous_section = None
        for node in sorted(
            graph["nodes"],
            key=lambda n: (section_for(n), n.get("name", n.get("text", ""))),
        ):
            ss = node.get("sources", []) + [
                s for c in node.get("content", []) for s in c["sources"]
            ]
            if not any(s["source_id"] == sid for s in ss):
                continue
            if section_for(node) != previous_section:
                previous_section = section_for(node)
                body.append("<h3>" + esc(previous_section) + "</h3>")
            scope = "; ".join(
                dict.fromkeys(
                    sections.get(locators[s["locator_id"]]["block_id"], "")
                    for s in ss
                    if s["locator_id"] in locators
                )
            )
            body.append(
                "<article id='"
                + esc(node["id"])
                + "'><h4>"
                + esc(node.get("name", node.get("text")))
                + "</h4><p>"
                + esc(node["type"])
                + " · "
                + esc(scope)
                + "</p><code>"
                + esc(node["id"])
                + "</code>"
            )
            for c in node.get("content", []):
                body.append(
                    "<p class='content'>"
                    + esc(c["text"])
                    + "</p>"
                    + source_html(c["sources"])
                )
            if node["type"] == "SampleQuestion":
                body.append(
                    "<p>"
                    + esc(node["options"])
                    + "</p><p>Đáp án nguồn: "
                    + esc(node["answer"])
                    + "</p>"
                    + source_html(node["sources"])
                )
            own = [r for r in reviews if r.get("record_id") == node["id"]]
            body.extend(
                "<p class='review'>"
                + esc(r["review_id"] + ": " + reason_text(r))
                + "</p>"
                for r in own
            )
            body.append("</article>")
    body.append("<h2>Quan hệ</h2>")
    for edge in graph["edges"]:
        left, right = node_by_id[edge["from_id"]], node_by_id[edge["to_id"]]
        body.append(
            "<article><b>"
            + esc(left.get("name", left.get("text")))
            + " → "
            + esc(edge["type"])
            + " → "
            + esc(right.get("name", right.get("text")))
            + "</b><p>Điều kiện: "
            + esc(edge["condition"])
            + "</p><code>"
            + esc(edge["id"])
            + "</code>"
            + source_html(edge["sources"])
            + "</article>"
        )
        body.extend(
            "<p class='review'>" + esc(r["review_id"] + ": " + reason_text(r)) + "</p>"
            for r in reviews
            if r.get("record_id") == edge["id"]
        )
    body.append("<h2>Danh sách cần đối chiếu / trích lại</h2>")
    for row in reviews:
        candidate = row.get("candidate", row.get("original", {}))
        label = (
            candidate.get("name", candidate.get("text", ""))
            if isinstance(candidate, dict)
            else ""
        )
        relation_label = (
            " → ".join(
                str(row.get(k, "")) for k in ("from_name", "relation_type", "to_name")
            )
            if row.get("from_name")
            else ""
        )
        body.append(
            "<details><summary>"
            + esc(row["review_id"] + " · " + reason_text(row))
            + "</summary><p>"
            + esc(label)
            + "</p><p>"
            + esc(relation_label)
            + "</p><p>PDF "
            + esc(row.get("pdf_page", "xem nguồn của bản ghi"))
            + "</p><blockquote>"
            + esc(row.get("excerpt", ""))
            + "</blockquote>"
            + source_html(row.get("source_contexts", []))
            + "<details><summary>Chi tiết kỹ thuật và đề xuất gốc</summary><pre>"
            + esc(__import__("json").dumps(row, ensure_ascii=False, indent=2))
            + "</pre></details></details>"
        )
    (output / "review.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>KG draft review</title><style>body{max-width:1080px;margin:32px auto;font:16px/1.6 system-ui;padding:0 20px}article{border:1px solid #ccd;padding:18px;margin:18px 0}code,small{overflow-wrap:anywhere}.content,blockquote{white-space:pre-wrap}.review{background:#fff3cf;padding:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        + "".join(body),
        encoding="utf-8",
    )
    (output / "report.md").write_text(
        f"# Bản nháp KG\n\n{len(graph['nodes'])} node, {len(graph['edges'])} cạnh; {len(reviews)} mục review; {len(audit.get('rejected', []))} rejected.\n\nMở [review.html](review.html) để đọc nội dung và nguồn theo sách/mục. Đây là bản nháp, không thay evidence/rubric của ứng dụng.\n\nChi tiết kỹ thuật: audit/report.json; draft-nodes.jsonl; draft-edges.jsonl; review-items.jsonl; rejected-items.jsonl.\n",
        encoding="utf-8",
    )
    return report
