"""Source structure for evidence inheritance; not page/chunk cooccurrence inference."""

import re
from copy import deepcopy

from document_toolkit.common import fingerprint
from knowledge_pipeline.validation import normalized


def structure_window(window):
    result, stack, system, categories, previous = [], [], None, {}, None
    for original in window["blocks"]:
        same_page = previous is None or original["pdf_page"] == previous["pdf_page"]
        if (previous and original["source_id"] != previous["source_id"]) or (
            not same_page and not original.get("continuation_verified")
        ):
            stack, system, categories = [], None, {}
        offset = original["char_start"]
        for raw_line in original["text"].splitlines(keepends=True):
            text = raw_line.rstrip("\r\n")
            if not text.strip():
                offset += len(raw_line)
                continue
            heading = re.match(r"^(\d+(?:\.\d+)*\.)\s+", text.strip())
            category = re.match(
                r"^\s*[-+•]\s*(?:Độ|Grade|Type|Stage|Nhóm)\s+([0-9IVX]+[a-zA-Z]?)\s*:",
                text,
            )
            is_system = (
                bool(
                    re.search(
                        r"^\s*(?:phân (?:độ|loại)|classification|grading).*:\s*$",
                        text,
                        re.IGNORECASE,
                    )
                )
                and not category
            )
            is_chapter = original.get("role") == "chapter_context"
            level = (
                0
                if is_chapter
                else len(heading.group(1).rstrip(".").split("."))
                if heading
                else None
            )
            if heading and original["role"] == "learning_objective":
                heading, level = None, None
            if level is not None:
                stack = [(depth, bid) for depth, bid in stack if depth < level]
                system, categories = None, {}
            block_id = (
                "SBLOCK2_" + fingerprint([original["block_id"], offset, text])[:24]
            )
            kind = (
                "heading"
                if heading or is_chapter
                else "system_heading"
                if is_system
                else "category"
                if category
                else "body"
            )
            parent_category = None
            code = category.group(1) if category else None
            if category:
                subcode = re.match(r"^(\d+|[IVX]+)([A-Ha-h])$", code)
                prefix = subcode.group(1) if subcode else None
                if (
                    prefix
                    and prefix in categories
                    and re.search(
                        r"chia ra|subdivid|subtype",
                        categories[prefix]["text"],
                        re.IGNORECASE,
                    )
                ):
                    parent_category = categories[prefix]["block_id"]
            block = {
                **original,
                "block_id": block_id,
                "text": text,
                "char_start": offset,
                "char_end": offset + len(text),
                "kind": kind,
                "order": len(result),
                "parent_heading_ids": [bid for _, bid in stack],
                "system_heading_id": system,
                "category_code": code,
                "parent_category_id": parent_category,
            }
            result.append(block)
            if level is not None:
                stack.append((level, block_id))
            if is_system:
                system, categories = block_id, {}
                block["system_heading_id"] = block_id
            if category:
                categories[code] = block
            offset += len(raw_line)
        previous = original
    return {
        **window,
        "blocks": result,
        "structure": [
            {
                "child_id": b["block_id"],
                "heading_path": b["parent_heading_ids"],
                "system_heading_id": b["system_heading_id"],
                "parent_category_id": b["parent_category_id"],
            }
            for b in result
        ],
    }


def structure_proves(relation, left, right, references, blocks):
    """Require a classification declaration + its actual list ancestry, not proximity."""
    if relation not in (
        "CLASSIFIED_BY",
        "HAS_CATEGORY",
        "IS_A",
        "MANAGED_BY",
        "APPLIES_TO",
    ):
        return False
    selected = [blocks[r["block_id"]] for r in references]
    names = [normalized(n["name"]).casefold() for n in (left, right)]
    left_blocks = [b for b in selected if names[0] in normalized(b["text"]).casefold()]
    right_blocks = [b for b in selected if names[1] in normalized(b["text"]).casefold()]
    if (
        relation == "APPLIES_TO"
        and left["type"] == "Skill"
        and right["type"] == "Intervention"
    ):
        action = " ".join(left["name"].split()[:2]).casefold()
        for body in selected:
            if (
                body.get("role") == "procedure"
                and action in normalized(body["text"]).casefold()
                and not re.match(
                    r"^\s*[-+•]?\s*(nếu|khi|if)\b", body["text"], re.IGNORECASE
                )
            ) and any(
                h["block_id"] in body.get("parent_heading_ids", [])
                and h.get("kind") == "heading"
                for h in right_blocks
            ):
                return True
        return False
    if not left_blocks or not right_blocks:
        return False
    for a in left_blocks:
        for b in right_blocks:
            if (
                relation == "HAS_CATEGORY"
                and b.get("kind") == "category"
                and b.get("system_heading_id") == a["block_id"]
                and a.get("kind") == "system_heading"
            ):
                return True
            if (
                relation == "IS_A"
                and a.get("kind") == "category"
                and a.get("parent_category_id") == b["block_id"]
            ):
                return True
            if (
                relation == "CLASSIFIED_BY"
                and b.get("kind") == "system_heading"
                and re.search(r"phân (?:độ|loại)", b["text"], re.IGNORECASE)
                and names[0] in normalized(b["text"]).casefold()
            ):
                return True
            if (
                relation == "MANAGED_BY"
                and a.get("kind") == "heading"
                and b.get("kind") == "heading"
                and a["block_id"] in b.get("parent_heading_ids", [])
                and re.search(
                    r"điều trị|xử trí|management|treatment", a["text"], re.IGNORECASE
                )
            ):
                return True
    return False


def expand_node_content(raw, blocks):
    """Retrieve child descriptions in the proven section, never synthesize missing knowledge."""
    result, events = deepcopy(raw), []
    if raw["type"] not in ("Classification", "Intervention"):
        return result, events
    for content in result["content"]:
        if any(s["block_id"] not in blocks for s in content["sources"]):
            # Unsupported model citations are a held record, just as in normal
            # source validation, not an uncaught KeyError aborting the batch.
            raise ValueError("unknown_block")
        references = [blocks[s["block_id"]] for s in content["sources"]]
        if not references or any(
            b.get("kind") not in ("heading", "system_heading") for b in references
        ):
            continue
        additions = []
        for heading in references:
            for child in blocks.values():
                is_category = (
                    raw["type"] == "Classification"
                    and child.get("kind") == "category"
                    and child.get("system_heading_id") == heading["block_id"]
                )
                is_step = (
                    raw["type"] == "Intervention"
                    and child.get("kind") == "body"
                    and child.get("role") == "procedure"
                    and heading["block_id"] in child.get("parent_heading_ids", [])
                )
                if is_category or is_step:
                    additions.append({"block_id": child["block_id"]})
        if additions:
            content["sources"].extend(additions)
            events.append(
                {
                    "node_local_id": raw["local_id"],
                    "reason": "retrieve_verified_child_description",
                    "added_sources": additions,
                }
            )
    return result, events


def normalize_edge_context(raw, nodes, blocks):
    """Normalize proposed edges only using explicit ancestor/list structure, with an audit trail."""
    result, events = deepcopy(raw), []
    if raw["from_id"] not in nodes or raw["to_id"] not in nodes:
        return result, events
    left, right = nodes[raw["from_id"]], nodes[raw["to_id"]]
    selected = [
        blocks[s["block_id"]] for s in raw["sources"] if s["block_id"] in blocks
    ]
    present = {s["block_id"] for s in raw["sources"]}
    if raw["type"] == "HAS_CATEGORY" and right["type"] == "ClassificationCategory":
        # The model may cite the declaration but omit the named bullet. Retrieve only
        # a uniquely matching child of that exact declaration / explicit parent list.
        for parent in list(selected):
            candidates = [
                b
                for b in blocks.values()
                if b.get("kind") == "category"
                and (
                    (
                        left["type"] == "Classification"
                        and b.get("system_heading_id") == parent["block_id"]
                        and parent.get("kind") == "system_heading"
                    )
                    or (
                        left["type"] == "ClassificationCategory"
                        and b.get("parent_category_id") == parent["block_id"]
                    )
                )
                and re.search(
                    re.escape(normalized(right["name"])) + r"(?=[:\s]|$)",
                    normalized(b["text"]),
                    re.IGNORECASE,
                )
            ]
            if len(candidates) == 1 and candidates[0]["block_id"] not in present:
                b = candidates[0]
                result["sources"].append({"block_id": b["block_id"]})
                present.add(b["block_id"])
                selected.append(b)
                events.append(
                    {
                        "edge_local_id": raw["local_id"],
                        "reason": "verified_list_child_citation",
                        "block_id": b["block_id"],
                    }
                )
    quoted = "\n".join(
        s.get("excerpt", blocks[s["block_id"]]["text"]) for s in result["sources"]
    )
    missing = [
        n
        for n in (left, right)
        if n.get("name")
        and n["type"] != "Skill"
        and normalized(n["name"]).casefold() not in normalized(quoted).casefold()
    ]
    for b in selected:
        ancestors = (
            list(b.get("parent_heading_ids", []))
            + ([b["system_heading_id"]] if b.get("system_heading_id") else [])
            + ([b["parent_category_id"]] if b.get("parent_category_id") else [])
        )
        for aid in ancestors:
            h = blocks[aid]
            is_list_parent = (
                aid == b.get("parent_category_id") and raw["type"] == "HAS_CATEGORY"
            )
            if aid not in present and (
                is_list_parent
                or any(
                    normalized(n["name"]).casefold() in normalized(h["text"]).casefold()
                    for n in missing
                )
            ):
                result["sources"].append({"block_id": aid})
                present.add(aid)
                events.append(
                    {
                        "edge_local_id": raw["local_id"],
                        "reason": "verified_ancestor_citation",
                        "block_id": aid,
                    }
                )
    if (
        raw["type"] == "MANAGED_BY"
        and left["type"] == "Condition"
        and right["type"] == "Intervention"
    ):
        for h in blocks.values():
            if (
                h.get("kind") != "heading"
                or normalized(right["name"]).casefold()
                not in normalized(h["text"]).casefold()
            ):
                continue
            for aid in h.get("parent_heading_ids", []):
                ancestor = blocks[aid]
                if (
                    normalized(left["name"]).casefold()
                    in normalized(ancestor["text"]).casefold()
                    and re.search(
                        r"điều trị|management|treatment",
                        ancestor["text"],
                        re.IGNORECASE,
                    )
                    and any(aid in b.get("parent_heading_ids", []) for b in selected)
                ):
                    for item in (ancestor, h):
                        if item["block_id"] not in present:
                            result["sources"].append({"block_id": item["block_id"]})
                            present.add(item["block_id"])
                            events.append(
                                {
                                    "edge_local_id": raw["local_id"],
                                    "reason": "explicit_treatment_heading_path",
                                    "block_id": item["block_id"],
                                }
                            )
    if (
        raw["type"] == "HAS_CATEGORY"
        and left["type"] == right["type"] == "ClassificationCategory"
    ) and structure_proves("IS_A", right, left, result["sources"], blocks):
        result["from_id"], result["to_id"], result["type"] = (
            raw["to_id"],
            raw["from_id"],
            "IS_A",
        )
        events.append(
            {
                "edge_local_id": raw["local_id"],
                "reason": "explicit_subcategory_structure",
                "original": raw,
                "normalized_type": "IS_A",
            }
        )
    return result, events
