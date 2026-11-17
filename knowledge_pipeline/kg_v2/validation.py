"""Source-grounding and graph-domain checks; not medical expert approval."""

import re
from copy import deepcopy

from document_toolkit.common import fingerprint
from knowledge_pipeline.validation import normalized

from .context import structure_proves
from .contracts import MEDICAL, RELATIONS
from .corrections import trace_raw


def source_entries(supports, blocks, locators, *, preserve_qualifiers=False):
    result = []
    for support in supports:
        block = blocks.get(support["block_id"])
        if block is None:
            raise ValueError("unknown_block")
        quote = support.get("excerpt", block["text"])
        if not quote.strip():
            raise ValueError("empty_quote")
        # Match whitespace only; never repair spelling, numbers or OCR symbols.
        pattern = r"\s+".join(re.escape(s) for s in normalized(quote).split())
        match = re.search(pattern, block["text"])
        if match is None:
            raise ValueError("quote_not_found")
        if preserve_qualifiers:
            # A verbatim substring can still be misleading if it drops "not", a dose,
            # or an exception from the same sentence/list item. Defer those fragments.
            boundaries = list(re.finditer(r"\n|[.!?](?=\s|$)", block["text"]))
            begin = max(
                (b.end() for b in boundaries if b.end() <= match.start()), default=0
            )
            finish = min(
                (b.start() for b in boundaries if b.end() >= match.end()),
                default=len(block["text"]),
            )
            omitted = (
                block["text"][begin : match.start()]
                + " "
                + block["text"][match.end() : finish]
            )
            if re.search(
                r"\d|[<>≤≥]|\b(không|chưa|nếu|khi|trừ|chỉ|phải|mg|ml|cm|mm|not|unless|if)\b|có thể",
                omitted,
                re.IGNORECASE,
            ):
                raise ValueError("quote_omits_condition_negation_or_numeric_context")
        raw = match.group()
        start, end = (
            block["char_start"] + match.start(),
            block["char_start"] + match.end(),
        )
        locator_id = (
            "LOC2_"
            + fingerprint(
                [block["source_id"], block["ocr_sha256"], block["pdf_page"], start, end]
            )[:24]
        )
        locators[locator_id] = {
            "locator_id": locator_id,
            "block_id": block["block_id"],
            "source_id": block["source_id"],
            "document_edition_id": block["document_edition_id"],
            "source_sha256": block["source_sha256"],
            "ocr_sha256": block["ocr_sha256"],
            "pdf_page": block["pdf_page"],
            "char_start": start,
            "char_end": end,
            "text": raw,
        }
        if block.get("correction"):
            trace = trace_raw(block["correction"], start, end)
            locators[locator_id].update(trace)
            locators[locator_id]["corrected_char_start"] = start
            locators[locator_id]["corrected_char_end"] = end
            locator = locators.pop(locator_id)
            locator_id = (
                "LOC2_"
                + fingerprint([locator_id, block["correction"]["revision"]])[:24]
            )
            locator["locator_id"] = locator_id
            locators[locator_id] = locator
        for issue in block.get("unresolved_issues", []):
            if issue["text"] in raw:
                raise ValueError("unresolved_ocr_affects_meaning")
        result.append(
            {
                "source_id": block["source_id"],
                "locator_id": locator_id,
                "pdf_pages": [block["pdf_page"]],
                "printed_pages": [block["printed_page_label"]]
                if block.get("printed_page_label")
                else [],
                "excerpt": raw,
            }
        )
    return result


def content_blocks(content, blocks, locators):
    result = []
    for item in content:
        sources = source_entries(
            item["sources"], blocks, locators, preserve_qualifiers=True
        )
        text = "\n".join(s["excerpt"] for s in sources)
        if all(
            blocks[s["block_id"]].get("kind") in ("heading", "system_heading")
            and not re.search(r":\s*\S.{12,}", blocks[s["block_id"]]["text"])
            for s in item["sources"]
        ):
            raise ValueError("title_only_content_is_not_medical_description")
        if "text" in item and normalized(item["text"]) != normalized(text):
            raise ValueError("content_changes_quote_or_qualifiers")
        result.append({"text": text, "sources": sources})
    return result


def supported_node(raw, blocks, locators):
    node = deepcopy(raw)
    kind = node["type"]
    if kind == "SampleQuestion":
        resolved_sources = source_entries(node["sources"], blocks, locators)
        if any(blocks[s["block_id"]]["role"] != "question" for s in node["sources"]):
            raise ValueError("question_not_in_book")
        source_block_ids = list(dict.fromkeys(s["block_id"] for s in node["sources"]))
        complete_question = "\n".join(blocks[k]["text"] for k in source_block_ids)
        if normalized(node["text"]) != normalized(complete_question):
            raise ValueError("question_context_or_subparts_omitted")
        if normalized(node["text"]) != normalized(
            "\n".join(s["excerpt"] for s in resolved_sources)
        ):
            raise ValueError("question_structure_changed")
        excerpts = "\n".join(s["excerpt"] for s in resolved_sources)
        if any(
            normalized(option) not in normalized(excerpts) for option in node["options"]
        ):
            raise ValueError("invented_question_option")
        if node["format"] == "multiple_choice":
            options = re.findall(r"(?m)^\s*[A-Za-z][.)]\s+(.+)$", complete_question)
            if not options or [normalized(s) for s in node["options"]] != [
                normalized(s) for s in options
            ]:
                raise ValueError("question_options_omitted_or_changed")
        resolved_answers = source_entries(node["answer_sources"], blocks, locators)
        answers = "\n".join(s["excerpt"] for s in resolved_answers)
        if node["answer"] is None and (
            node["answer_sources"] or node["explanation"] is not None
        ):
            raise ValueError("answer_without_book_answer")
        if node["answer"] is not None:
            if not node["answer_sources"] or any(
                blocks[s["block_id"]]["role"] != "answer"
                for s in node["answer_sources"]
            ):
                raise ValueError("invented_answer")
            for field in ("answer", "explanation"):
                if node[field] is not None and normalized(
                    node[field]
                ) not in normalized(answers):
                    raise ValueError("invented_answer_or_explanation")
        node["sources"] = source_entries(node["sources"], blocks, locators)
        node["answer_sources"] = source_entries(
            node["answer_sources"], blocks, locators
        )
        identity = node["sources"]
    else:
        identity = source_entries(node["identity_sources"], blocks, locators)
        identity_text = "\n".join(s["excerpt"] for s in identity)
        if kind in MEDICAL:
            if (
                normalized(node["name"]).casefold()
                not in normalized(identity_text).casefold()
            ):
                raise ValueError("name_not_supported")
            for alias in node["aliases"]:
                if normalized(alias).casefold() not in normalized(
                    identity_text
                ).casefold() or not re.search(
                    r"còn gọi|hay gọi|tên khác|also called|known as",
                    identity_text,
                    re.IGNORECASE,
                ):
                    raise ValueError("alias_equivalence_not_supported")
        else:
            source_entries(node["basis_sources"], blocks, locators)
            roles = {blocks[s["block_id"]]["role"] for s in node["basis_sources"]}
            allowed = {
                "learning_objective": {"learning_objective"},
                "practice_requirement": {"practice_requirement"},
                "procedural_instruction": {"procedure"},
            }[node["basis"]]
            if not roles <= allowed:
                raise ValueError("skill_has_no_explicit_basis")
            verbs = r"^(Giải thích|Phân tích|Minh họa|Vận dụng|Trình bày|Nhận diện|Đánh giá|Thực hiện|Phân loại|Chẩn đoán|Phân biệt|Nhận biết|Mô tả|So sánh|Lựa chọn|Theo dõi|Phòng ngừa|Thực hành|Sử dụng|Xử lý|Xử trí|Explain|Perform)\s+\S+"
            if not re.search(verbs, node["name"], re.IGNORECASE):
                raise ValueError("skill_name_needs_action_and_object")
            if node["basis"] == "learning_objective":
                action = re.search(verbs, node["name"], re.IGNORECASE).group(1)
                basis_text = "\n".join(
                    s["excerpt"]
                    for s in source_entries(node["basis_sources"], blocks, locators)
                )
                if action.casefold() not in basis_text.casefold():
                    raise ValueError("skill_action_not_in_objective")
            if node["kind"] == "practical" and (
                node["basis"] == "learning_objective"
                or re.match(
                    r"^(Giải thích|Phân tích|Minh họa|Trình bày|Explain)\b",
                    node["name"],
                    re.IGNORECASE,
                )
            ):
                raise ValueError("theory_does_not_prove_practical_skill")
            node.pop("basis")
            node.pop("basis_sources")
        node["content"] = content_blocks(node["content"], blocks, locators)
        node.pop("identity_sources")
    # Source-anchored identity, not a name/embedding-only merge. Cross-source identity requires review.
    identity_key = fingerprint(
        [
            kind,
            normalized(node.get("name", node.get("text", ""))).casefold(),
            node.get("kind"),
            sorted(
                (s["source_id"], s["locator_id"], normalized(s["excerpt"]))
                for s in identity
            ),
        ]
    )
    node.pop("local_id")
    node["id"] = "CAND2_" + identity_key[:24]
    return node, identity_key


def check_edge(raw, local_nodes, blocks, locators):
    if raw["from_id"] not in local_nodes or raw["to_id"] not in local_nodes:
        raise ValueError("dangling_edge_or_rejected_node")
    left, right = local_nodes[raw["from_id"]], local_nodes[raw["to_id"]]
    domain, range_ = RELATIONS[raw["type"]]
    if left["type"] not in domain or right["type"] not in range_:
        raise ValueError("invalid_relationship_end_types")
    if raw["type"] == "IS_A" and left["type"] != right["type"]:
        raise ValueError("is_a_incompatible_taxonomy")
    sources = source_entries(raw["sources"], blocks, locators, preserve_qualifiers=True)
    text = "\n".join(s["excerpt"] for s in sources)
    contextual = structure_proves(raw["type"], left, right, raw["sources"], blocks)
    condition = raw["condition"]
    if condition is not None and (
        not condition.strip() or normalized(condition) not in normalized(text)
    ):
        raise ValueError("condition_not_in_source")
    if not contextual and re.search(
        r"\b(không|chưa|không được|chống chỉ định|not|never)\b", text, re.IGNORECASE
    ):
        raise ValueError("negative_edge_requires_manual_review")
    if (
        re.search(r"\b(nếu|khi|trừ|ngoại trừ|tùy|if|unless)\b", text, re.IGNORECASE)
        and not condition
        and not contextual
    ):
        raise ValueError("edge_loses_condition")
    if (
        "có thể" in text.lower()
        and raw["type"] != "MAY_CAUSE"
        and not condition
        and not contextual
    ):
        raise ValueError("edge_loses_modality")
    for endpoint in (left, right):
        if (
            endpoint["type"] in MEDICAL
            and (
                normalized(endpoint["name"]).casefold()
                not in normalized(text).casefold()
            )
            and not contextual
        ):
            raise ValueError("edge_end_not_mentioned_in_own_evidence")
    if (
        raw["type"] in ("CLASSIFIED_BY", "HAS_CATEGORY")
        or (raw["type"] == "IS_A" and left["type"] == "ClassificationCategory")
    ) and not contextual:
        raise ValueError("classification_edge_requires_verified_structure")
    if (
        raw["type"] == "IS_A"
        and not contextual
        and not re.search(r"là|loại|thuộc|gồm|is a|type of", text, re.IGNORECASE)
    ):
        raise ValueError("is_a_not_explicit")
    cues = {
        "LOCATED_IN": r"\b(ở|tại|vùng|trên|dưới|trong)\b",
        "HAS_FINDING": r"biểu hiện|triệu chứng|dấu hiệu|chảy|lộ|đau|sưng",
        "CLASSIFIED_BY": r"phân loại|phân độ|chia",
        "HAS_CATEGORY": r"phân loại|phân độ|gồm|chia|độ [123IV]",
        "EVALUATED_BY": r"chẩn đoán|x quang|chụp|xét nghiệm|thăm dò|doppler",
        "MANAGED_BY": r"điều trị|xử lý|xử trí|phẫu thuật|cấp cứu",
        "USES_DRUG": r"dùng|sử dụng|thuốc|kháng sinh",
        "MAY_CAUSE": r"gây|dẫn đến|biến chứng|hậu quả",
        "GUIDED_BY": r"nguyên tắc|hướng dẫn|theo",
        "HAS_SUBSKILL": r"gồm|các bước|bao gồm|bước",
    }
    if raw["type"] in cues and not re.search(cues[raw["type"]], text, re.IGNORECASE):
        raise ValueError("edge_has_no_explicit_relation_cue")
    if raw["type"] in ("APPLIES_TO", "REQUIRES_KNOWLEDGE_OF") and any(
        blocks[s["block_id"]]["role"]
        not in ("learning_objective", "procedure", "practice_requirement")
        for s in raw["sources"]
    ):
        raise ValueError("skill_edge_not_in_explicit_requirement")
    if raw["type"] == "ASSESSES":
        if any(blocks[s["block_id"]]["role"] != "question" for s in raw["sources"]):
            raise ValueError("assessment_mapping_not_supported_by_question")
        action = right["name"].split()[0]
        if action.casefold() not in text.casefold():
            raise ValueError("assessment_action_not_in_question")
    edge = {
        "from_id": left["id"],
        "to_id": right["id"],
        "type": raw["type"],
        "condition": condition,
        "sources": sources,
    }
    # Conditions and evidence are part of assertion identity; do not collapse to a triple.
    edge["id"] = "KG2E_" + fingerprint(edge)[:24]
    return edge


def cycle_if_added(edges, edge):
    if edge["type"] not in ("IS_A", "HAS_SUBSKILL"):
        return False
    adjacency = {}
    for item in edges:
        if item["type"] == edge["type"]:
            adjacency.setdefault(item["from_id"], []).append(item["to_id"])
    todo, seen = [edge["to_id"]], set()
    while todo:
        current = todo.pop()
        if current == edge["from_id"]:
            return True
        if current not in seen:
            seen.add(current)
            todo.extend(adjacency.get(current, []))
    return False
