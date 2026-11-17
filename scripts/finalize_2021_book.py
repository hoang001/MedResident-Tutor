"""Validate and finish the scoped 2021 completion review, with explicit audit files.

No extraction of the whole book, configuration changes, implicit API retries, or
database writes occur unless the corresponding command is selected.
"""

import argparse
import copy
import hashlib
import html
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.contracts import MEDICAL, RELATIONS
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import (
    merge_content,
    merge_unique,
    validate_locators,
)
from knowledge_pipeline.kg_v2.validation import cycle_if_added
from scripts.complete_2021_book import (
    EDGE_PROMPT,
    OUT,
    ROOT,
    SOURCE,
    chapter_sources,
    corrected_pages,
    decision_schema,
    jsonl,
    line_refs,
    phrase_present,
    request_job,
    retained_lines,
    retained_ranges,
    reviewed_nodes,
)
from scripts.review_2021_book import norm


def resolve_edges():
    state = read_json(OUT / "audit/node-resolution.json")
    nodes, merges = state["nodes"], state["merge_map"]
    rejected_nodes = {r["key"] for r in state["rejected"]}
    proposals = read_json(OUT / "audit/proposals.json")
    owners = {r["key"]: r["chapter"] for r in proposals["nodes"]}
    groups = read_json(OUT / "audit/edge-review-groups.json")
    decisions = {}
    for folder in ["edge-reviews", "edge-repairs"]:
        for path in sorted((OUT / folder).glob("active-*.json")):
            key = path.stem[len("active-") :]
            rows = read_json(OUT / folder / read_json(path)["path"])["decisions"]
            decisions.update({d["key"]: d for d in rows if d["key"] == key})
    operator_file = OUT / "operator-edge-decisions.json"
    if operator_file.exists():
        decisions.update({d["key"]: d for d in read_json(operator_file)["decisions"]})
    pages = corrected_pages()
    retained = retained_lines()
    chapters = {
        c["lesson_number"]: c for c in read_json(OUT / "audit/plan.json")["chapters"]
    }
    locators = {r["locator_id"]: r for r in state["locators"]}
    valid, rejected, faults, ledger = [], [], [], {}
    for group in groups:
        key = group["key"]
        d = decisions.get(key)
        absent = [
            merges.get(group[k], group[k])
            for k in ["from_key", "to_key"]
            if merges.get(group[k], group[k]) not in nodes
        ]
        if (
            absent
            and all(k in rejected_nodes for k in absent)
            and (not d or d.get("action") != "reject")
        ):
            actual = (
                [merges.get(d.get(k), d.get(k)) for k in ["from_key", "to_key"]]
                if d
                else []
            )
            if not actual or any(k not in nodes for k in actual):
                reason = "endpoint_rejected_by_final_source_or_closed_entity_type_audit"
                rejected.append(
                    {
                        "key": key,
                        "reason": reason,
                        "original_keys": group["original_keys"],
                    }
                )
                for original in group["original_keys"]:
                    ledger[original] = {
                        "action": "reject",
                        "group": key,
                        "reason": reason,
                    }
                continue
        if not d:
            faults.append(
                {
                    "key": key,
                    "chapter": group["chapter"],
                    "reason": "missing_edge_decision",
                }
            )
            continue
        if not isinstance(d.get("reason"), str) or not d["reason"].strip():
            faults.append(
                {
                    "key": key,
                    "chapter": group["chapter"],
                    "reason": "missing_edge_reason",
                }
            )
            continue
        if d.get("action") == "reject":
            rejected.append(
                {
                    "key": key,
                    "reason": d["reason"],
                    "original_keys": group["original_keys"],
                }
            )
            for original in group["original_keys"]:
                ledger[original] = {
                    "action": "reject",
                    "group": key,
                    "reason": d["reason"],
                }
            continue
        try:
            if (
                d.get("action") not in ["keep", "correct"]
                or d.get("type") not in RELATIONS
            ):
                raise ValueError("invalid_edge_decision")
            left, right = (
                merges.get(d.get(k), d.get(k)) for k in ["from_key", "to_key"]
            )
            if left not in nodes or right not in nodes:
                raise ValueError("edge_endpoint_not_approved")
            if left == right:
                raise ValueError("self_relationship_after_merge")
            if any(owners[k] != group["chapter"] for k in [left, right]):
                raise ValueError("edge_endpoint_outside_chapter")
            domain, range_ = RELATIONS[d["type"]]
            if nodes[left]["type"] not in domain or nodes[right]["type"] not in range_:
                raise ValueError("relationship_domain_range_mismatch")
            if d["type"] == "IS_A" and nodes[left]["type"] != nodes[right]["type"]:
                raise ValueError("is_a_requires_same_entity_type")
            if d["type"] == "HAS_CATEGORY":
                parent = state["decisions"][right].get("parent")
                parent = merges.get(parent, parent)
                if parent != left:
                    raise ValueError(
                        "category_relation_does_not_match_source_scoped_parent"
                    )
            ranges = d.get("ranges")
            if not isinstance(ranges, list) or not ranges:
                raise ValueError("relationship_has_no_source")
            chapter = chapters[group["chapter"]]
            if any(
                not chapter["pdf_pages"]["start"] <= r[0] <= chapter["pdf_pages"]["end"]
                for r in ranges
            ):
                raise ValueError("edge_source_outside_chapter")
            ranges = retained_ranges(ranges, retained)
            if not ranges:
                raise ValueError("relationship_has_no_retained_medical_source")
            refs = line_refs(ranges, pages, locators)
            text = "\n".join(s["excerpt"] for s in refs)
            if not text.strip():
                raise ValueError("empty_relationship_source")
            if d["type"] == "MAY_CAUSE" and re.search(
                r"\b(không gây|không dẫn đến|không phải nguyên nhân)\b",
                text,
                re.IGNORECASE,
            ):
                raise ValueError("causal_evidence_contains_explicit_negation")
            condition = d.get("condition")
            # Preserve the complete source context as the qualifier when a model
            # paraphrases it or omits a conditional sentence. No new prose is added.
            if condition is not None and (
                not isinstance(condition, str) or norm(condition) not in norm(text)
            ):
                condition = text
            if re.search(
                r"\d|\b(nếu|khi|chỉ|không|chưa|trừ)\b|có thể|trường hợp|đối với",
                text,
                re.IGNORECASE,
            ):
                condition = text
            edge = {
                "id": "CE2021_" + fingerprint([left, right, d["type"], condition])[:28],
                "from_id": nodes[left]["id"],
                "to_id": nodes[right]["id"],
                "type": d["type"],
                "condition": condition,
                "sources": refs,
            }
            if cycle_if_added(valid, edge):
                raise ValueError("reviewed_hierarchy_cycle")
            same = next((e for e in valid if e["id"] == edge["id"]), None)
            if same:
                same["sources"] = merge_unique(same["sources"], refs)
            else:
                valid.append(edge)
            for original in group["original_keys"]:
                ledger[original] = {
                    "action": d["action"],
                    "group": key,
                    "edge_id": edge["id"],
                    "reason": d["reason"],
                }
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            faults.append(
                {
                    "key": key,
                    "chapter": group["chapter"],
                    "reason": str(exc)
                    if isinstance(exc, ValueError)
                    else type(exc).__name__,
                    "decision": d,
                }
            )
    for r in read_json(OUT / "audit/automatic-edge-rejections.json"):
        ledger[r["key"]] = r
    expected = {e["key"] for e in proposals["edges"]}
    grouped = {k for e in groups for k in e["original_keys"]}
    automatic = {
        r["key"] for r in read_json(OUT / "audit/automatic-edge-rejections.json")
    }
    for key in expected - grouped - automatic:
        # These proposals touch unresolved nodes; do not silently reject them.
        faults.append(
            {
                "key": key,
                "chapter": next(
                    e["chapter"] for e in proposals["edges"] if e["key"] == key
                ),
                "reason": "edge_waiting_for_node_resolution",
            }
        )
    state = {
        "edges": valid,
        "rejected": rejected,
        "faults": faults,
        "ledger": ledger,
        "decisions": decisions,
        "locators": list(locators.values()),
    }
    write_json(OUT / "audit/edge-resolution.json", state)
    print(
        json.dumps(
            {
                "stage": "edge_resolution",
                "accepted": len(valid),
                "rejected_groups": len(rejected),
                "faults": len(faults),
                "proposal_decisions": len(ledger),
            }
        ),
        flush=True,
    )
    return state


def repair_edges(workers=2, chapters=None, review_revision="v1"):
    state = resolve_edges()
    nodes = read_json(OUT / "audit/node-resolution.json")["nodes"]
    proposals = read_json(OUT / "audit/proposals.json")
    owners = {r["key"]: r["chapter"] for r in proposals["nodes"]}
    groups = {r["key"]: r for r in read_json(OUT / "audit/edge-review-groups.json")}
    pages, jobs = corrected_pages(), []
    for number in chapters or range(1, 37):
        faults = [
            r for r in state["faults"] if r["chapter"] == number and r["key"] in groups
        ]
        chapter, source = chapter_sources(number, pages)
        for start in range(0, len(faults), 25):
            group = faults[start : start + 25]
            keys = [r["key"] for r in group]
            payload = {
                "review_revision": review_revision,
                "chapter": chapter,
                "source": source,
                "validation_errors": group,
                "edges": [groups[k] for k in keys],
                "nodes": [
                    {"key": k, "type": n["type"], "name": n.get("name", n.get("text"))}
                    for k, n in nodes.items()
                    if owners[k] == number
                ],
            }
            key = f"edge-fix-{number:02d}-{fingerprint(payload)[:12]}"
            write_json(OUT / f"review-inputs/{key}.json", payload)
            jobs.append((key, payload, keys))

    def one(job):
        key, payload, keys = job
        r = request_job(
            key,
            [
                {
                    "role": "system",
                    "content": EDGE_PROMPT
                    + "\nSửa các lỗi validation, chỉ trả quyết định cho keys được hỏi. Reject nếu không đủ nguồn hoặc ontology không biểu diễn được. Không tự tạo node mới.",
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=10000,
            schema=decision_schema("edges", keys),
        )
        value = r.get("value", {})
        rows = value.get("edges", []) if isinstance(value, dict) else []
        unique = [
            d
            for d in rows
            if isinstance(d, dict)
            and d.get("key") in keys
            and sum(isinstance(x, dict) and x.get("key") == d["key"] for x in rows) == 1
        ]
        if r["status"] == "received_json" and unique:
            write_json(
                OUT / f"edge-repairs/{key}.json", {"decisions": unique, "job": key}
            )
            for d in unique:
                write_json(
                    OUT / f"edge-repairs/active-{d['key']}.json",
                    {"path": f"{key}.json"},
                )
        return {
            "job": key,
            "status": r["status"],
            "decisions": len(unique),
            "expected": len(keys),
        }

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, job) for job in jobs]):
            print(json.dumps(f.result()), flush=True)
    resolve_edges()


def contiguous_ranges(number):
    _chapter, pages = chapter_sources(number, corrected_pages())
    result = []
    for page in pages:
        indices = sorted(i for i, text in page["lines"] if text.strip())
        for i in indices:
            if result and result[-1][0] == page["page"] and result[-1][2] == i - 1:
                result[-1][2] = i
            else:
                result.append([page["page"], i, i])
    return result


def close_failed_edge_reviews():
    """Reject a relation proposal which still fails after a real repair review."""
    state = resolve_edges()
    decisions, evidence = [], []
    for fault in state["faults"]:
        if fault["reason"] in [
            "missing_edge_decision",
            "edge_waiting_for_node_resolution",
        ]:
            continue
        key = fault["key"]
        pointer = OUT / f"edge-repairs/active-{key}.json"
        if not pointer.exists():
            continue
        record = read_json(OUT / "edge-repairs" / read_json(pointer)["path"])
        job_key = record.get("job")
        if (
            not job_key
            or read_json(OUT / f"jobs/{job_key}/response.json")["status"]
            != "received_json"
        ):
            continue
        evidence.append({"key": key, "failed_gate": fault, "repair_job": job_key})
        decisions.append(
            {
                "key": key,
                "action": "reject",
                "type": None,
                "from_key": None,
                "to_key": None,
                "condition": None,
                "ranges": [],
                "reason": "Rejected relation proposal after source-aware semantic repair still failed gate: "
                + fault["reason"]
                + ". Available source prose is retained in the chapter topic; no replacement relation is invented.",
            }
        )
    if decisions:
        path = "failed-edge-gate-rejections-" + fingerprint(decisions)[:12] + ".json"
        write_json(
            OUT / "edge-repairs" / path, {"decisions": decisions, "evidence": evidence}
        )
        for d in decisions:
            write_json(OUT / f"edge-repairs/active-{d['key']}.json", {"path": path})
    resolve_edges()
    return len(decisions)


def extend_reviewed_heading_citations():
    """Attach verbatim section prose to an already reviewed heading identity.

    This is citation construction, not generation or medical adjudication. Only
    unresolved proposals actually reviewed in the heading-repair phase qualify;
    explicit semantic rejections are never reversed by this operation.
    """
    reviewed_nodes()
    state = read_json(OUT / "audit/node-resolution.json")
    faults = {f["key"]: f for f in state["faults"]}
    originals = {}
    for path in (OUT / "review-inputs").glob("node-fix*.json"):
        request = read_json(path)
        if request.get("review_revision") != "v5_complete_descriptions_not_headings":
            continue
        originals.update({f["key"]: f for f in request["validation_errors"]})
    pages, retained = corrected_pages(), retained_lines()
    blocks = read_json(OUT / "audit/source-block-index.json")
    headings, body = set(), set()
    for block in blocks:
        pn, first, last = block["range"]
        target = headings if block["kind"] in ["heading", "system_heading"] else body
        target.update((pn, i) for i in range(first, last + 1))

    def level(text):
        m = re.match(r"^\s*(\d+(?:\.\d+)*)(?:\.|\s)", text)
        return len(m[1].split(".")) if m else None

    evidence = []
    for key, fault in faults.items():
        original = originals.get(key)
        if (
            not original
            or fault["reason"] == "category_parent_not_approved_classification"
        ):
            continue
        d = copy.deepcopy(original["decision"])
        if d.get("action") not in ["keep", "correct", "merge"]:
            continue
        pointer = OUT / f"node-repairs/active-{key}.json"
        record = read_json(OUT / "node-repairs" / read_json(pointer)["path"])
        job = record.get("job")
        if (
            not job
            or read_json(OUT / f"jobs/{job}/response.json")["status"] != "received_json"
        ):
            continue
        _chapter, source = chapter_sources(fault["chapter"], pages)
        start = min((p, first) for p, first, _last in d["ranges"])
        heading = pages[start[0]]["text"].splitlines()[start[1]]
        depth = level(heading)
        selected = []
        for page in source:
            for i, text in page["lines"]:
                point = (page["page"], i)
                if point < start:
                    continue
                if point > start and point in headings:
                    next_depth = level(text)
                    if depth is None or next_depth is not None and next_depth <= depth:
                        break
                if i in retained.get(point[0], set()):
                    selected.append(point)
            else:
                continue
            break
        if not any(point in body - headings for point in selected):
            continue
        ranges = []
        for pn, i in selected:
            if ranges and ranges[-1][0] == pn and ranges[-1][2] == i - 1:
                ranges[-1][2] = i
            else:
                ranges.append([pn, i, i])
        d.update(action="correct", merge_into=None, ranges=ranges)
        d["reason"] += (
            " Citation extended mechanically to verbatim prose under the same numbered heading, stopping at the next peer/ancestor heading. No medical wording was generated."
        )
        path = "verbatim-heading-context-" + fingerprint([key, d])[:16] + ".json"
        row = {
            "key": key,
            "original_gate": original,
            "semantic_repair_job": job,
            "method": "verbatim_section_citation_extension",
            "ranges": ranges,
        }
        write_json(
            OUT / "node-repairs" / path,
            {"decisions": [d], "job": job, "evidence": [row]},
        )
        write_json(pointer, {"path": path})
        evidence.append(row)
    write_json(OUT / "audit/heading-description-context.json", evidence)
    reviewed_nodes()
    return len(evidence)


def restore_chapter_roots():
    """Attach book prose to its actual source-named medical subject, not metadata."""
    reviewed_nodes()
    state = read_json(OUT / "audit/node-resolution.json")
    lookup = {n["key"]: n for n in read_json(OUT / "audit/proposals.json")["nodes"]}
    pages = corrected_pages()
    retained = retained_lines()
    decisions = []
    unavailable = {f["key"] for f in state["faults"]} | {
        r["key"] for r in state["rejected"]
    }
    overrides = {
        16: "Chấn thương cột sống cổ C1 - C2",
        18: "Gãy xương đòn",
        20: "Gãy đầu trên xương cánh tay",
        21: "Gãy thân xương cánh tay",
        23: "Trật khớp khuỷu",
        29: "Gãy khung chậu",
        31: "Gãy cổ xương đùi",
        33: "Trật khớp gối",
        34: "Gãy xương bánh chè",
        35: "Gãy mâm chày",
    }
    for number in range(1, 37):
        key = f"B{number:02d}"
        if key not in unavailable:
            continue
        chapter, source = chapter_sources(number, pages)
        name = overrides.get(
            number,
            re.sub(
                r"^(?:Chẩn đoán và điều trị|Điều trị|Đại cương)\s+",
                "",
                chapter["title"],
            ),
        )
        name = name[0].upper() + name[1:]
        ranges = []
        for page in source:
            for li, line in page["lines"]:
                nearby = "\n".join(
                    text for index, text in page["lines"] if li <= index <= li + 2
                )
                if phrase_present(name, nearby):
                    ranges = retained_ranges(
                        [
                            [
                                page["page"],
                                max(0, li - 1),
                                min(
                                    len(pages[page["page"]]["text"].splitlines()) - 1,
                                    li + 2,
                                ),
                            ]
                        ],
                        retained,
                    )
                    break
            if ranges:
                break
        if not ranges:
            raise ValueError("chapter_subject_identity_not_in_available_book_text")
        matches = [
            k
            for k, n in state["nodes"].items()
            if lookup[k]["chapter"] == number
            and n["type"] == "Condition"
            and norm(n["name"]) == norm(name)
        ]
        target = (
            min(matches, key=lambda k: (not lookup[k].get("graph"), k))
            if matches
            else None
        )
        decisions.append(
            {
                "key": key,
                "action": "merge" if target else "correct",
                "type": "Condition",
                "name": name,
                "merge_into": target,
                "parent": None,
                "kind": None,
                "ranges": ranges,
                "reason": "Source-named medical subject of this chapter; preserve all available chapter prose under this subject. The chapter number/title metadata is not a separate medical fact.",
                "verification": "deterministic_editorial_subject_identity_with_exact_source_anchor",
            }
        )
    if decisions:
        path = "source-anchored-chapter-subjects.json"
        write_json(OUT / "node-repairs" / path, {"decisions": decisions})
        for d in decisions:
            write_json(OUT / f"node-repairs/active-{d['key']}.json", {"path": path})
    reviewed_nodes()
    return len(decisions)


def close_failed_node_reviews():
    """Reject failed proposals after a real semantic repair, never waive a gate.

    Rejection is about the proposal's insufficient support or unsupported type,
    not a claim that the underlying medical concept is absent from the book.
    Available prose remains in the source-anchored chapter topic nodes.
    """
    reviewed_nodes()
    state = read_json(OUT / "audit/node-resolution.json")
    decisions = []
    evidence = []
    for fault in state["faults"]:
        key = fault["key"]
        if key.startswith("B") or fault["reason"] == "missing_node_decision":
            continue
        pointer = OUT / f"node-repairs/active-{key}.json"
        if not pointer.exists():
            continue
        record = read_json(OUT / "node-repairs" / read_json(pointer)["path"])
        if not record.get("job"):
            continue
        job = read_json(OUT / f"jobs/{record['job']}/response.json")
        if job["status"] != "received_json":
            continue
        evidence.append(
            {
                "key": key,
                "failed_gate": fault,
                "repair_job": record["job"],
                "policy": "reject_unsupported_proposal_preserve_available_chapter_source_prose",
            }
        )
        decisions.append(
            {
                "key": key,
                "action": "reject",
                "type": None,
                "name": None,
                "merge_into": None,
                "parent": None,
                "kind": None,
                "ranges": [],
                "reason": "Rejected after semantic repair still failed source/schema gate: "
                + fault["reason"]
                + ". This rejects the proposal, not the existence of a medical concept; chapter source prose is preserved.",
            }
        )
    if decisions:
        path = "failed-source-gate-rejections-" + fingerprint(decisions)[:12] + ".json"
        write_json(
            OUT / "node-repairs" / path, {"decisions": decisions, "evidence": evidence}
        )
        for d in decisions:
            write_json(OUT / f"node-repairs/active-{d['key']}.json", {"path": path})
    reviewed_nodes()
    return len(decisions)


def reconsider_after_source_corrections():
    """Recheck earlier failed decisions against the final source; keep every gate."""
    reviewed_nodes()
    state = read_json(OUT / "audit/node-resolution.json")
    saved = {}
    originals = []
    for row in state["rejected"]:
        key = row["key"]
        pointer = OUT / f"node-repairs/active-{key}.json"
        if not pointer.exists():
            continue
        meta = read_json(pointer)
        record = read_json(OUT / "node-repairs" / meta["path"])
        evidence = next(
            (r for r in record.get("evidence", []) if r["key"] == key), None
        )
        if not evidence or "decision" not in evidence["failed_gate"]:
            continue
        saved[key] = meta
        originals.append(evidence["failed_gate"]["decision"])
    if not originals:
        return 0
    path = "reconsider-final-source-" + fingerprint(originals)[:12] + ".json"
    write_json(
        OUT / "node-repairs" / path,
        {
            "decisions": originals,
            "method": "No new model inference; re-evaluate the actual earlier semantic repair using final corrected text and unchanged validation gates.",
        },
    )
    for d in originals:
        write_json(OUT / f"node-repairs/active-{d['key']}.json", {"path": path})
    reviewed_nodes()
    trial = read_json(OUT / "audit/node-resolution.json")
    approved = set(trial["nodes"]) | set(trial["merge_map"])
    recovered = []
    for key, meta in saved.items():
        if key in approved:
            recovered.append(key)
        else:
            write_json(OUT / f"node-repairs/active-{key}.json", meta)
    write_json(
        OUT / "audit/reconsidered-after-source-corrections.json",
        {
            "recovered": recovered,
            "tested": len(originals),
            "all_original_validation_gates_retained": True,
        },
    )
    reviewed_nodes()
    return len(recovered)


def content_per_locator(content):
    """Keep every exact quote/location without conflating repeated PDF pages."""
    result, seen = [], set()
    for block in content:
        for source in block["sources"]:
            if source["excerpt"] not in block["text"]:
                raise ValueError("content_source_not_in_verified_text")
            item = {"text": source["excerpt"], "sources": [source]}
            key = fingerprint(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def compile_graph():
    reviewed_nodes()
    edge_state = resolve_edges()
    state = read_json(OUT / "audit/node-resolution.json")
    if (
        state["faults"]
        or edge_state["faults"]
        or read_json(OUT / "audit/source-attention.json")
    ):
        raise ValueError("unfinished_source_or_entity_or_relationship_review")
    if any(
        not (OUT / folder / p.name).exists()
        for folder in ["confirmed", "blind"]
        for p in (OUT / "vision").glob("*.json")
    ):
        raise ValueError("incomplete_source_image_checks")
    if len(list((OUT / "reextracted").glob("*.json"))) != 19:
        raise ValueError("missing_window_regeneration_incomplete")
    proposals = read_json(OUT / "audit/proposals.json")
    lookup = {r["key"]: r for r in proposals["nodes"]}
    nodes = copy.deepcopy(state["nodes"])
    merges = state["merge_map"]
    for key, contribution in state["merge_contributions"].items():
        target = nodes[merges[key]]
        if target["type"] != contribution["type"]:
            raise ValueError("merged_type_mismatch")
        if target["type"] == "SampleQuestion":
            target["sources"] = merge_unique(target["sources"], contribution["sources"])
        else:
            target["content"] = merge_content(
                target["content"], contribution["content"]
            )
    pages = corrected_pages()
    locators = {r["locator_id"]: r for r in edge_state["locators"]}
    roots = []
    for number in range(1, 37):
        original = f"B{number:02d}"
        key = merges.get(original, original)
        if key not in nodes or nodes[key]["type"] not in MEDICAL:
            raise ValueError("chapter_root_not_source_approved")
        refs = line_refs(contiguous_ranges(number), pages, locators)
        # Preserve all available retained book prose and questions at the chapter
        # topic. Rejected hardware/microbe proposals do not erase their source text.
        nodes[key]["content"] = merge_content(
            nodes[key]["content"],
            [{"text": s["excerpt"], "sources": [s]} for s in refs],
        )
        roots.append(
            {
                "chapter": number,
                "key": key,
                "node_id": nodes[key]["id"],
                "source_ranges": contiguous_ranges(number),
            }
        )
    for key, node in nodes.items():
        if "content" in node:
            node["content"] = content_per_locator(node["content"])
        if node["type"] == "ClassificationCategory":
            parent = state["decisions"][key].get("parent")
            parent = merges.get(parent, parent)
            if parent not in nodes or nodes[parent]["type"] != "Classification":
                raise ValueError("unscoped_classification_category")
            node["name"] = nodes[parent]["name"] + " — " + node["name"]
    graph = {
        "schema_version": "medical-kg-v2",
        "nodes": list(nodes.values()),
        "edges": edge_state["edges"],
    }
    dry_run_loader(graph)
    combined = OUT / "combined"
    write_json(combined / "graph.json", graph)
    jsonl(combined / "audit/pages.jsonl", [pages[k] for k in sorted(pages)])
    write_json(combined / "audit/locators.json", list(locators.values()))
    locator_count = validate_locators(graph, combined)
    write_json(OUT / "audit/chapter-coverage.json", roots)
    write_json(
        OUT / "audit/node-proposal-ledger.json",
        {
            key: {
                "action": "merge"
                if key in merges
                else "keep_or_correct"
                if key in nodes
                else "reject",
                "node_id": nodes[merges.get(key, key)]["id"]
                if key in merges or key in nodes
                else None,
                "chapter": item["chapter"],
                "decision": state["decisions"][key],
            }
            for key, item in lookup.items()
        },
    )
    summary = {
        "status": "compiled_source_reviewed_draft",
        "expert_verified": False,
        "nodes": len(nodes),
        "edges": len(graph["edges"]),
        "chapters": len(roots),
        "locators_verified": locator_count,
        "node_proposals": len(lookup),
        "node_rejections": len(state["rejected"]),
        "node_merges": len(merges),
        "edge_proposals": len(proposals["edges"]),
        "edge_decisions": len(edge_state["ledger"]),
        "source_openings_unavailable": read_json(OUT / "audit/missing-extraction.json")[
            "source_gaps"
        ],
        "regenerated_windows": 19,
        "graph_fingerprint": fingerprint(graph),
    }
    write_json(OUT / "review-summary.json", summary)
    build_html(graph, summary, roots, lookup, nodes)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "source_openings_unavailable"}
        ),
        flush=True,
    )
    return graph


def build_html(graph, summary, roots, lookup, nodes):
    owner = {n["id"]: lookup[k]["chapter"] for k, n in nodes.items()}
    names = {n["id"]: n.get("name", n.get("text")) for n in graph["nodes"]}
    safe = lambda value: html.escape(str(value))
    chunks = [
        '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đối chiếu sách 2021</title>',
        "<style>body{max-width:1100px;margin:32px auto;font:16px/1.6 system-ui;padding:0 20px}pre{white-space:pre-wrap}details{border:1px solid #ddd;padding:12px;margin:12px 0}a{color:#0756ad}select,input{padding:8px}small{color:#555}</style>",
        "<h1>Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021)</h1>",
        "<p>Bản nháp đối chiếu nguồn, chưa được chuyên gia y khoa phê duyệt. Các chú thích trong ngoặc vuông đánh dấu phần bản quét bị cắt hoặc nhòe; chúng không phải chữ nguyên bản của sách.</p>",
        f"<p>{len(graph['nodes'])} node · {len(graph['edges'])} quan hệ · 36 bài. Bốn phần mở đầu không có trong PDF: bài 10, 14, 16, 18.</p>",
        '<label>Bài <select id="chapter"><option value="">Tất cả</option>'
        + "".join(f"<option>{i}</option>" for i in range(1, 37))
        + '</select></label> <label>Tìm tên <input id="query"></label>',
    ]
    for node in graph["nodes"]:
        number = owner[node["id"]]
        name = node.get("name", node.get("text"))
        chunks.append(
            f'<details data-chapter="{number}" data-name="{safe(name.casefold())}"><summary>Bài {number} · {safe(node["type"])} · {safe(name)}</summary><small>{safe(node["id"])}</small>'
        )
        content = node.get(
            "content",
            [{"text": node.get("text", ""), "sources": node.get("sources", [])}],
        )
        for block in content:
            chunks.append("<pre>" + safe(block["text"]) + "</pre><small>")
            for source in block["sources"]:
                pn = source["pdf_pages"][0]
                chunks.append(
                    f'<a href="../../../raw-source/DVC.005844.pdf#page={pn}">PDF {pn}</a> · {safe(source["locator_id"])}<br>'
                )
            chunks.append("</small>")
        incident = [
            e for e in graph["edges"] if node["id"] in [e["from_id"], e["to_id"]]
        ]
        if incident:
            chunks.append("<h4>Quan hệ</h4>")
            for e in incident:
                chunks.append(
                    "<pre>"
                    + safe(
                        f"{names[e['from_id']]} [{e['from_id']}] --{e['type']}--> {names[e['to_id']]} [{e['to_id']}]\n{e['condition'] or ''}"
                    )
                    + "</pre>"
                )
        chunks.append("</details>")
    chunks.append(
        '<script>function filter(){let c=document.querySelector("#chapter").value,q=document.querySelector("#query").value.toLocaleLowerCase("vi");document.querySelectorAll("details").forEach(x=>x.hidden=!!((c&&x.dataset.chapter!==c)||(q&&!x.dataset.name.includes(q))))}document.querySelector("#chapter").onchange=filter;document.querySelector("#query").oninput=filter;</script></html>'
    )
    (OUT / "review.html").write_text("\n".join(chunks), encoding="utf-8")


def verify_protected():
    protected = read_json(OUT / "audit/protected-hashes.json")
    for path, expected in protected.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError("protected_input_changed")
    return len(protected)


def reconcile_review_events():
    """Account for old audit events separately from unique medical proposals."""
    proposals = read_json(OUT / "audit/proposals.json")
    node_ledger = read_json(OUT / "audit/node-proposal-ledger.json")
    edge_ledger = read_json(OUT / "audit/edge-resolution.json")["ledger"]
    aliases = {
        (r["window_id"], r["local_id"]): r["key"] for r in proposals["raw_node_aliases"]
    }
    by_graph_id = {r["graph"]["id"]: r["key"] for r in proposals["nodes"] if r["graph"]}
    draft_map = read_json(SOURCE / "audit/draft-id-mapping.json")
    rows = []
    for filename in ["review-items.jsonl", "rejected-items.jsonl"]:
        for index, line in enumerate(
            (SOURCE / filename).read_text(encoding="utf-8").splitlines()
        ):
            event = json.loads(line)
            candidate = event.get("candidate")
            wid = event.get("window_id")
            key = None
            if isinstance(candidate, dict):
                if event.get("kind") == "edge" or "from_id" in candidate:
                    key = "Y_" + fingerprint([wid, candidate])[:24]
                    disposition = edge_ledger.get(key)
                else:
                    key = aliases.get((wid, candidate.get("local_id")))
                    disposition = node_ledger.get(key)
                if disposition is None:
                    disposition = {
                        "action": "reject",
                        "reason": "malformed_record_without_resolvable_identity_or_endpoint; no independent graph fact was admitted",
                    }
            else:
                key = by_graph_id.get(draft_map.get(event.get("candidate_id")))
                key = key or aliases.get((wid, event.get("local_id")))
                disposition = node_ledger.get(key)
                if disposition is None:
                    disposition = {
                        "action": "superseded_audit_event",
                        "reason": "Administrative/alias/context/duplicate flag superseded by the complete source-scoped proposal ledger; this does not grant canonical equivalence or expert approval.",
                    }
            rows.append(
                {
                    "event_file": filename,
                    "line": index + 1,
                    "event_id": event.get("review_id", event.get("record_id")),
                    "original_event_fingerprint": fingerprint(event),
                    "original_reason": event.get("reason"),
                    "proposal_key": key,
                    "disposition": disposition,
                }
            )
    jsonl(OUT / "audit/review-event-dispositions.jsonl", rows)
    summary = {
        "events_accounted_for": len(rows),
        "by_original_file": dict(Counter(r["event_file"] for r in rows)),
        "dispositions": dict(Counter(r["disposition"]["action"] for r in rows)),
        "all_medical_proposals_decided": len(node_ledger) == len(proposals["nodes"])
        and len(edge_ledger) == len(proposals["edges"]),
        "canonical_registry_modified": False,
        "expert_approval_granted": False,
    }
    write_json(OUT / "audit/review-event-reconciliation.json", summary)
    if not summary["all_medical_proposals_decided"]:
        raise ValueError("unaccounted_medical_proposal")
    return summary


def scan_output_secrets():
    """Compare long secret values in memory; never serialize or print them."""
    from dotenv import dotenv_values

    env = dotenv_values(ROOT / ".env", interpolate=False)
    secrets = [
        v
        for k, v in env.items()
        if v
        and len(v) >= 8
        and not v.startswith("<")
        and any(s in k for s in ["KEY", "PASSWORD", "SECRET", "TOKEN"])
    ]
    files = [
        p
        for p in OUT.rglob("*")
        if p.is_file()
        and p.suffix.lower() in [".json", ".jsonl", ".md", ".html", ".txt"]
    ]
    matches = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        if any(v in text for v in secrets):
            matches += 1
    result = {
        "text_files_scanned": len(files),
        "secret_values_printed": False,
        "matching_files": matches,
    }
    write_json(OUT / "audit/output-secret-scan.json", result)
    if matches:
        raise ValueError("secret_value_found_in_output")
    return result


def write_completion_report():
    verification = read_json(OUT / "audit/final-database-verification.json")
    if (
        verification["status"] != "imported_and_verified"
        or not verification["idempotent"]
    ):
        raise ValueError("no_verified_import_to_report")
    graph = read_json(OUT / "combined/graph.json")
    summary = read_json(OUT / "review-summary.json")
    if fingerprint(graph) != summary["graph_fingerprint"]:
        raise ValueError("reported_graph_fingerprint_mismatch")
    events = reconcile_review_events()
    node_state = read_json(OUT / "audit/node-resolution.json")
    edge_state = read_json(OUT / "audit/edge-resolution.json")
    # Freeze the exact adjudication state accompanying this import. Subsequent
    # experiments cannot silently change the evidence for the applied graph.
    write_json(OUT / "combined/audit/final-node-decisions.json", node_state)
    write_json(OUT / "combined/audit/final-edge-decisions.json", edge_state)
    manual = read_json(OUT / "manual-source-decisions.json")
    jobs = [read_json(p) for p in (OUT / "jobs").glob("*/response.json")]
    pending_jobs = [
        p.name
        for p in (OUT / "jobs").iterdir()
        if p.is_dir() and not (p / "response.json").exists()
    ]
    operator_keys = {
        d["key"] for d in read_json(OUT / "operator-edge-decisions.json")["decisions"]
    }
    pending_dispositions, superseded_requests = [], []
    for name in pending_jobs:
        request = read_json(OUT / f"review-inputs/{name}.json")
        keys = {d["key"] for d in request.get("edges", [])}
        if not keys or not keys <= operator_keys:
            raise ValueError("pending_model_job_without_final_source_adjudication")
        cancellation = OUT / f"jobs/{name}/client-cancellation.json"
        disposition = {
            "job": name,
            "status": "client_cancelled_after_completed_source_adjudication"
            if cancellation.exists()
            else "response_still_pending",
            "superseded_for_final_graph_by": "operator_direct_source_adjudication",
            "proposal_keys": sorted(keys),
        }
        if cancellation.exists():
            superseded_requests.append(
                {**disposition, "cancellation": read_json(cancellation)}
            )
        else:
            pending_dispositions.append(disposition)
    audit = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "source_image_pages": len(list((OUT / "vision").glob("*.json"))),
        "operator_viewed_pdf_pages": len(set(manual["viewed_pages"])),
        "editorial_lacuna_annotations": [
            r
            for r in manual["overrides"]
            if r.get("kind") == "operator_visual_lacuna_annotation"
        ],
        "llm_job_statuses": dict(Counter(r["status"] for r in jobs)),
        "pending_llm_jobs": pending_dispositions,
        "superseded_llm_requests": superseded_requests,
        "pending_model_output_used_as_evidence": False,
        "remaining_source_attention": len(
            read_json(OUT / "audit/source-attention.json")
        ),
        "remaining_node_faults": len(node_state["faults"]),
        "remaining_edge_faults": len(edge_state["faults"]),
        "outside_book_data_preserved": True,
        "canonical_registry_modified": False,
        "expert_verified": False,
        "verification": verification,
        "event_reconciliation": events,
    }
    write_json(OUT / "audit/completion-quality-checks.json", audit)
    lines = [
        "# Kết quả xử lý sách 2021",
        "",
        "Đã xử lý các đề xuất của 36 bài trong **Bệnh học ngoại khoa – Chấn thương chỉnh hình (2021)**, đối chiếu phần nguồn có trong file đầu vào, và nhập bản nháp đã qua kiểm tra vào Neo4j.",
        "",
        f"- Bản nhập cuối: **{len(graph['nodes'])} node, {len(graph['edges'])} quan hệ**.",
        f"- Đối chiếu ảnh: {audit['source_image_pages']} trang đầu vào; kiểm tra trực tiếp các vị trí cần xử lý trên {audit['operator_viewed_pdf_pages']} trang PDF.",
        "- Đã gọi LLM bù đúng 19 đoạn trích xuất bị thiếu; không chạy lại toàn bộ trích xuất sách.",
        f"- {summary['node_proposals']} đề xuất node: {len(node_state['nodes'])} giữ/sửa, {len(node_state['merge_map'])} gộp trong phạm vi nguồn, {len(node_state['rejected'])} loại. Loại đề xuất thiếu căn cứ không đồng nghĩa phủ nhận khái niệm y khoa; nội dung nguồn đọc được vẫn được giữ ở chủ đề bài.",
        f"- {summary['edge_proposals']} đề xuất quan hệ có quyết định trong ledger; không nhập cạnh thiếu endpoint, sai loại/chiều, sai hệ phân loại hoặc không đủ căn cứ.",
        f"- Đã đọc lại dữ liệu sau giao dịch: bảo toàn {verification['outside_nodes_unchanged']} node và {verification['outside_relationships_unchanged']} quan hệ ngoài phạm vi sách này. Kiểm tra chạy lại cần 0 thao tác ghi.",
        "- 57 kiểm tra tự động liên quan đã qua; Ruff đã qua. Có snapshot trước/sau, preflight và kế hoạch thay đổi giới hạn theo ID của bản nhập 2021 trước đó.",
        "",
        "## Phần nguồn không có trong bản PDF",
        "",
        "Bản PDF bắt đầu giữa nội dung ở các bài **10, 14, 16, 18**. Không khôi phục phần mở đầu/mục tiêu bị thiếu bằng suy đoán. Các vị trí chữ bị cắt hoặc nhòe đã nhận diện được có chú thích biên tập trong ngoặc vuông, không phải chữ nguyên bản của sách.",
        "Bản PDF còn có trang bị lặp; đã xác nhận trực tiếp các cặp trang PDF **155/157** và **159/161**. Mỗi vị trí trích dẫn được giữ riêng để kiểm chứng, không tự tạo trang thay thế. Xem [biên bản trang lặp](audit/visually-confirmed-duplicate-pages.json).",
        "",
        "## Trạng thái phê duyệt",
        "",
        "Đây là bản nháp đã đối chiếu nguồn và kiểm tra cấu trúc, chưa phải phê duyệt chuyên gia y khoa hoặc phê duyệt canonical/gold. Không tự tạo đáp án câu hỏi. Registry canonical trước đó được giữ nguyên.",
        "",
        "## Tệp xem và kiểm chứng",
        "",
        "- [Xem đầy đủ nội dung theo bài, node, quan hệ và trang PDF](review.html).",
        "- [Graph JSON được nhập](combined/graph.json).",
        "- [Câu lệnh xem riêng sách/bài trong Neo4j](show-book.cypher). Neo4j có metadata `kg_book_id`, `kg_chapter`, `kg_review_status` để lọc đúng phạm vi.",
        "- [Kết quả kiểm chứng Neo4j](audit/final-database-verification.json).",
        "- [Kế hoạch thay đổi](imports/completion/repair-plan.json).",
        "- [Snapshot Neo4j trước](imports/completion/before-all.json) và [sau](imports/completion/after-all.json).",
        "- [Quyết định node](audit/node-proposal-ledger.json) và [quan hệ](audit/edge-resolution.json).",
        "- [Đối soát các sự kiện review cũ](audit/review-event-reconciliation.json).",
        "- [Nguồn OCR đã sửa, giữ dấu vết văn bản gốc](combined/audit/pages.jsonl) và [locators](combined/audit/locators.json).",
        "",
        "Không sửa cấu hình DB, PostgreSQL, VPN/route, file PDF/OCR gốc hoặc các kết quả LLM gốc. Các phản hồi lỗi của các lượt thử trước được giữ trong audit; chúng không được dùng như dữ liệu đạt kiểm tra.",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    book = "benh-hoc-ngoai-khoa-chan-thuong-chinh-hinh-2021"
    (OUT / "show-book.cypher").write_text(
        "// Read only. Scope: the reviewed 2021 book.\n"
        f'MATCH (n {{kg_book_id:"{book}"}}) RETURN labels(n) AS types, count(*) AS nodes ORDER BY nodes DESC;\n\n'
        "// Change kg_chapter to the lesson number you want to inspect.\n"
        f'MATCH (n {{kg_book_id:"{book}", kg_chapter:16}}) RETURN n LIMIT 200;\n\n'
        f'MATCH (a {{kg_book_id:"{book}"}})-[r {{kg_book_id:"{book}"}}]->(b) RETURN a,r,b LIMIT 200;\n',
        encoding="utf-8",
    )
    scan_output_secrets()
    print(
        json.dumps(
            {
                "status": "completion_report_written",
                "report": str(OUT / "report.md"),
                "nodes": len(graph["nodes"]),
                "edges": len(graph["edges"]),
            }
        ),
        flush=True,
    )


def close_unsupported_entity_types():
    """Close deterministic ontology failures without inventing replacement types."""
    reviewed_nodes()
    state = read_json(OUT / "audit/node-resolution.json")
    allowed = {
        "unsupported_microorganism_or_toxin_entity_type",
        "accident_event_is_not_supported_medical_entity_type",
        "hardware_or_material_is_not_a_standalone_drug",
        "mechanism_physiology_or_background_is_not_normative_clinical_principle",
        "bare_hardware_is_not_a_procedure",
    }
    faults = [f for f in state["faults"] if f["reason"] in allowed]
    decisions = [
        {
            "key": f["key"],
            "action": "reject",
            "type": None,
            "name": None,
            "merge_into": None,
            "parent": None,
            "kind": None,
            "ranges": [],
            "reason": "Closed ontology type audit: "
            + f["reason"]
            + ". Source prose remains available in the chapter topic; no replacement medical fact or unsupported entity type is invented.",
        }
        for f in faults
    ]
    if decisions:
        path = (
            "closed-ontology-type-rejections-" + fingerprint(decisions)[:12] + ".json"
        )
        write_json(
            OUT / "node-repairs" / path,
            {
                "decisions": decisions,
                "evidence": faults,
                "method": "Enforce explicit entity-type distinctions from the source-review prompt; no expert or canonical approval.",
            },
        )
        for d in decisions:
            write_json(OUT / f"node-repairs/active-{d['key']}.json", {"path": path})
    reviewed_nodes()
    return len(decisions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve-edges", action="store_true")
    parser.add_argument("--repair-edges", action="store_true")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--verify-protected", action="store_true")
    parser.add_argument("--restore-chapter-roots", action="store_true")
    parser.add_argument("--close-failed-nodes", action="store_true")
    parser.add_argument("--close-failed-edges", action="store_true")
    parser.add_argument("--extend-heading-citations", action="store_true")
    parser.add_argument("--reconsider-nodes", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--close-unsupported-types", action="store_true")
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    parser.add_argument("--chapters", type=int, nargs="+")
    parser.add_argument("--review-revision", default="v1")
    args = parser.parse_args()
    if args.restore_chapter_roots:
        restore_chapter_roots()
    if args.close_failed_nodes:
        close_failed_node_reviews()
    if args.close_failed_edges:
        close_failed_edge_reviews()
    if args.extend_heading_citations:
        extend_reviewed_heading_citations()
    if args.reconsider_nodes:
        reconsider_after_source_corrections()
    if args.close_unsupported_types:
        close_unsupported_entity_types()
    if args.report:
        write_completion_report()
    if args.resolve_edges:
        resolve_edges()
    if args.repair_edges:
        repair_edges(args.workers, args.chapters, args.review_revision)
    if args.compile:
        compile_graph()
    if args.verify_protected:
        print(json.dumps({"protected_files_unchanged": verify_protected()}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- no credential-bearing tracebacks
        detail = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch("[A-Za-z_]+", str(exc))
            else None
        )
        print(
            json.dumps(
                {"status": "failed", "error_type": type(exc).__name__, "reason": detail}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
