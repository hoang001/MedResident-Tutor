"""Prepare the remaining 2006 book offline; preserves numbered sections and tables.

This writes scopes/audits only. It neither calls an LLM nor touches Neo4j.
"""

import argparse
import copy
import html
import json
import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import Settings
from knowledge_pipeline.kg_v2.contracts import MEDICAL, RELATIONS, schemas
from knowledge_pipeline.kg_v2.draft_run import DRAFT_INSTRUCTION, messages_for
from knowledge_pipeline.kg_v2.pipeline import HERE, ROOT, prepare

CHAPTERS = [
    (1, "Vết thương phần mềm", 8),
    (2, "Gãy xương ở trẻ em", 12),
    (3, "Gãy xương hở", 16),
    (4, "Gãy xương có biến chứng thần kinh", 27),
    (5, "Gãy xương có biến chứng mạch máu", 34),
    (6, "Hội chứng chèn ép khoang", 37),
    (7, "Cắt cụt chi", 46),
    (8, "Nối lại chi bị đứt rời", 50),
    (9, "Vết thương khớp", 59),
    (10, "Viêm xương cấp tính", 61),
    (11, "Hoại thư sinh hơi", 63),
    (12, "Nhiễm trùng bàn tay", 67),
    (13, "Đại cương về bỏng", 77),
    (14, "U xương", 83),
    (15, "Trật khớp vai", 89),
    (16, "Trật khớp khuỷu", 93),
    (17, "Trật khớp háng", 98),
    (18, "Gãy 2 xương cẳng tay", 105),
    (19, "Vết thương bàn tay", 114),
    (20, "Chấn thương cột sống", 123),
    (21, "Gãy xương chậu", 130),
    (22, "Gãy cổ xương đùi", 142),
    (23, "Gãy thân xương đùi", 150),
    (24, "Gãy thân 2 xương cẳng chân", 156),
    (25, "Các thương tổn ở cổ chân", 163),
]


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", html.unescape(text)).split())


class ImageText(HTMLParser):
    """Identify model image descriptions from the OCR artifact's image labels."""

    def __init__(self):
        super().__init__()
        self.divs = []
        self.descriptions = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            self.divs.append({"label": attrs.get("data-label"), "text": []})
        if tag == "img" and attrs.get("alt"):
            self.descriptions.add(normalized(attrs["alt"]))

    def handle_data(self, data):
        for div in self.divs:
            div["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self.divs:
            div = self.divs.pop()
            if div["label"] == "Image":
                self.descriptions.add(normalized(" ".join(div["text"])))


def heading_depth(text):
    match = re.match(r"^(\d+(?:\.\d+)*)(?:\.\s+|\s+)", text)
    if not match:
        return None
    if "." not in match[1] and not text[len(match[1]) :].startswith(". "):
        return None  # "21 ngày" is clinical prose, not a heading.
    return len(match[1].split("."))


def known_skips():
    """Skip generation, not medical verification, for the two completed scopes."""
    shoulder = (
        ROOT
        / "data/knowledge-extraction/v2/chapter-shoulder-2006-source-review-20261102/import-manifest.json"
    )
    elbow = (
        ROOT / "data/knowledge-extraction/v2/chapter-elbow-2006-wait/batch-state.json"
    )
    first = read_json(shoulder)
    second = read_json(elbow)
    if first.get("status") != "source_compared_and_imported":
        raise ValueError("shoulder_skip_not_supported_by_manifest")
    report = second["latest_result"]
    if report["windows_total"] != 9 or report["windows_with_raw_output"] != 9:
        raise ValueError("elbow_skip_requires_nine_processed_windows")
    return {
        15: {
            "reason": "Đã có extraction toàn phạm vi PDF89–92 và overlay đối chiếu nguồn đã import; Kocher vẫn giữ ngoài.",
            "existing_result": shoulder.parent.relative_to(ROOT).as_posix(),
        },
        16: {
            "reason": "Đã xử lý 9/9 cửa sổ extraction PDF93–97; còn 4 node giữ ngoài và chưa kiểm nguồn toàn bài. Bỏ gọi lại, không đánh dấu đã review xong.",
            "existing_result": second["latest_aggregate"],
        },
    }


def selectors_for(lines, role, pages):
    """Exact unique anchors; joins adjacent lines without swallowing an exclusion."""
    runs = []
    for page, number in lines:
        if runs and runs[-1][0] == page and runs[-1][2] == number:
            runs[-1] = (page, runs[-1][1], number + 1)
        else:
            runs.append((page, number, number + 1))
    result = []
    for page, lo, hi in runs:
        row = pages[page]
        raw = row["text"]
        parts = raw.splitlines(keepends=True)
        start = sum(map(len, parts[:lo]))
        end = sum(map(len, parts[:hi]))
        while end > start and raw[end - 1] in "\r\n":
            end -= 1
        value = raw[start:end]
        start_anchor = value if raw.find(value) == start else raw[start:]
        end_anchor = raw[end:] if end < len(raw) else None
        assert raw.index(start_anchor) == start
        assert end_anchor is None or raw.index(end_anchor, start) == end
        result.append(
            {
                "pdf_page": page,
                "start_anchor": start_anchor,
                "end_anchor": end_anchor,
                "role": role,
                "continuation_verified": role != "chapter_context",
            }
        )
    return result


def make_units(start, end, pages):
    units, stack, exclusions, kept = [], [], [], set()
    current = None

    def close():
        nonlocal current
        if current and current["lines"]:
            units.append(current)
        current = None

    for page in range(start, end + 1):
        row = pages[page]
        lines = row["text"].splitlines()
        images = ImageText()
        images.feed(row.get("html", ""))
        retained = []
        for i, line in enumerate(lines):
            reason = None
            if not line.strip():
                reason = "empty_line"
            elif page == start and i == 0:
                reason = "chapter_heading_kept_as_context"
            elif i == len(lines) - 1 and re.fullmatch(r"\d{1,3}", line.strip()):
                reason = "trailing_printed_page_number"
            elif re.match(r"^Hình\s+\d", line, re.IGNORECASE):
                reason = "numbered_figure_caption"
            elif normalized(line) in images.descriptions:
                reason = "ocr_image_description_not_book_prose"
            if reason:
                exclusions.append(
                    {"pdf_page": page, "line": i, "text": line, "reason": reason}
                )
            else:
                retained.append((page, i))
                kept.add((page, i))
        # A table and its page context remain atomic; original table_html is sent.
        if re.search(r"<table\b", row.get("html", ""), re.IGNORECASE):
            close()
            parents = [h for _, h in stack]
            units.append(
                {
                    "lines": retained,
                    "parents": parents,
                    "role": "table",
                    "heading": f"Bảng và nội dung đi kèm PDF{page}",
                }
            )
            for ref in retained:
                line = lines[ref[1]]
                depth = heading_depth(line)
                if depth is not None:
                    stack = [(d, h) for d, h in stack if d < depth] + [(depth, ref)]
            continue
        for ref in retained:
            line = lines[ref[1]]
            depth = heading_depth(line)
            if depth is not None:
                close()
                stack = [(d, h) for d, h in stack if d < depth]
                current = {
                    "lines": [],
                    "parents": [h for _, h in stack],
                    "role": "medical_text",
                    "heading": line,
                }
                stack.append((depth, ref))
            if current is None:
                current = {
                    "lines": [],
                    "parents": [h for _, h in stack],
                    "role": "medical_text",
                    "heading": line[:100],
                }
            current["lines"].append(ref)
    close()
    for unit in units:
        if unit["role"] == "table":
            continue
        path = (
            " ".join(pages[p]["text"].splitlines()[i] for p, i in unit["parents"])
            + " "
            + unit["heading"]
        )
        if re.search(
            r"điều trị|xử trí|phương pháp|kỹ thuật|phẫu thuật|nắn|bất động",
            path,
            re.IGNORECASE,
        ):
            unit["role"] = "procedure"
    return units, exclusions, kept


def window_for(number, title, start, groups, pages, serial):
    selectors = selectors_for([(start, 0)], "chapter_context", pages)
    # Restore only the opening ancestor headings; all following sections are in
    # source order. Never split a numbered leaf, a procedure or a table by page.
    if groups:
        selectors += selectors_for(groups[0]["parents"], "medical_text", pages)
    for unit in groups:
        selectors += selectors_for(unit["lines"], unit["role"], pages)
    return {
        "key": f"bai-{number:02d}-phan-{serial:03d}",
        "section_id": f"book-2006-bai-{number:02d}-phan-{serial:03d}",
        "title": f"Bài {number}. {title} — {groups[0]['heading']}",
        "selectors": selectors,
    }


def window_bytes(window, pages):
    blocks = []
    for selector in window["selectors"]:
        row = pages[selector["pdf_page"]]
        text = row["text"]
        start = text.index(selector["start_anchor"])
        end = (
            text.index(selector["end_anchor"], start)
            if selector["end_anchor"]
            else len(text)
        )
        block = {"text": text[start:end], "role": selector["role"]}
        if selector["role"] == "table":
            block["table_html"] = "\n".join(
                re.findall(
                    r"<table\b.*?</table>",
                    row.get("html", ""),
                    re.IGNORECASE | re.DOTALL,
                )
            )
        blocks.append(block)
    return len(json.dumps(blocks, ensure_ascii=False).encode())


def prepare_book(plan_path, audit_path):
    if plan_path.exists() or audit_path.exists():
        raise ValueError("new_book_plan_and_audit_required")
    skips = known_skips()
    ocr_path = ROOT / "data/graduate/Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi.json"
    ocr = read_json(ocr_path)
    pages = {r["page_start"]: r for r in ocr["sections"]}
    template = read_json(HERE / "chapter-elbow-2006-shard-01.json")
    template["documents"][0]["verified_printed_labels"] = {}
    template.pop("ocr_patches", None)
    template.pop("ocr_issues", None)
    settings = Settings.from_env()
    prompt = (HERE / "extract-v2.txt").read_text(encoding="utf-8") + DRAFT_INSTRUCTION
    prompt += "\nCONTROLLED NODE TYPES: " + ", ".join(
        MEDICAL + ["Skill", "SampleQuestion"]
    )
    prompt += "\nCONTROLLED EDGE ENDPOINT TYPES:\n" + "\n".join(
        name + ": " + "|".join(sorted(domain)) + " -> " + "|".join(sorted(range_))
        for name, (domain, range_) in RELATIONS.items()
    )
    schema_message = {
        "role": "system",
        "content": "Return JSON matching this JSON Schema:\n"
        + json.dumps(schemas()[0], ensure_ascii=False),
    }
    scopes, plans, chapters, excluded, coverage = [], [], [], [], []
    folder = HERE / (plan_path.stem.removesuffix("-plan") + "-scopes")
    if folder.exists():
        raise ValueError("new_book_scope_folder_required")
    max_payload, max_prompt = 0, 0
    for offset, (number, title, start) in enumerate(CHAPTERS):
        end = CHAPTERS[offset + 1][2] - 1 if offset + 1 < len(CHAPTERS) else 168
        record = {
            "lesson_number": number,
            "title": title,
            "pdf_pages": {"start": start, "end": end},
            "ocr_heading": pages[start]["text"].splitlines()[0],
        }
        if number in skips:
            chapters.append(
                {
                    **record,
                    "generation_status": "skipped_existing_extraction",
                    **skips[number],
                }
            )
            continue
        units, drop, kept = make_units(start, end, pages)
        excluded.extend(drop)
        windows = []
        chunk = []
        unit_groups = []
        for unit in units:
            trial = window_for(
                number, title, start, chunk + [unit], pages, len(windows) + 1
            )
            size = window_bytes(trial, pages)
            root_section = unit["parents"][0] if unit["parents"] else unit["lines"][0]
            previous_root = (
                (
                    chunk[0]["parents"][0]
                    if chunk[0]["parents"]
                    else chunk[0]["lines"][0]
                )
                if chunk
                else None
            )
            if chunk and (
                size > 4500
                or len(chunk) >= 3
                or root_section != previous_root
                or unit["role"] == "table"
                or chunk[0]["role"] == "table"
            ):
                windows.append(
                    window_for(number, title, start, chunk, pages, len(windows) + 1)
                )
                unit_groups.append(chunk)
                chunk = []
            chunk.append(unit)
            if (
                window_bytes(
                    window_for(number, title, start, chunk, pages, len(windows) + 1),
                    pages,
                )
                > 12000
            ):
                raise ValueError(f"atomic_section_exceeds_budget_lesson_{number}")
        if chunk:
            windows.append(
                window_for(number, title, start, chunk, pages, len(windows) + 1)
            )
            unit_groups.append(chunk)
        # The actual prompt also contains per-line IDs, ancestry and JSON schema.
        # Refine only between whole units until that real prompt fits; source text
        # is never truncated and numbered leaves/tables are never cut to fit.
        refined = []
        pending = list(unit_groups)
        while pending:
            group = pending.pop(0)
            candidate = window_for(number, title, start, group, pages, len(refined) + 1)
            probe = copy.deepcopy(template)
            probe["documents"][0]["windows"] = [candidate]
            test = prepare(probe)
            if len(test["windows"]) != 1 or test["preparation_rejected"]:
                fits = False
            else:
                messages = [schema_message, *messages_for(test["windows"][0], prompt)]
                fits = (
                    sum(len(m["content"].encode()) + 128 for m in messages)
                    <= settings.prompt_budget_bytes
                )
            if fits:
                refined.append(group)
            else:
                if len(group) < 2:
                    raise ValueError(
                        f"atomic_unit_exceeds_prompt_budget_lesson_{number}"
                    )
                midpoint = len(group) // 2
                pending[0:0] = [group[:midpoint], group[midpoint:]]
        unit_groups = refined
        windows = [
            window_for(number, title, start, group, pages, i + 1)
            for i, group in enumerate(refined)
        ]
        covered = {ref for group in unit_groups for u in group for ref in u["lines"]}
        if covered != kept:
            raise ValueError("source_line_coverage_mismatch")
        coverage.append(
            {
                "lesson_number": number,
                "retained_lines": len(kept),
                "covered_lines": len(covered),
                "missing_lines": [],
                "atomic_units": len(units),
                "windows": len(windows),
                "table_pages": [
                    p
                    for p in range(start, end + 1)
                    if re.search(r"<table\b", pages[p].get("html", ""), re.IGNORECASE)
                ],
            }
        )
        chapters.append(
            {
                **record,
                "generation_status": "scheduled",
                "windows": len(windows),
                "shards": (len(windows) + 2) // 3,
            }
        )
        for a in range(0, len(windows), 3):
            shard = a // 3 + 1
            scope = copy.deepcopy(template)
            scope["documents"][0]["survey_sections"] = [
                {
                    "key": f"book-2006-bai-{number:02d}",
                    "original_title": f"Bài {number}. {title}",
                    "parent_key": None,
                    "pdf_pages": {"start": start, "end": end},
                    "printed_pages": None,
                    "boundary_status": "provided_ocr_chapter_headings_not_inferred_from_toc_page_numbers",
                }
            ]
            scope["documents"][0]["windows"] = windows[a : a + 3]
            prepared = prepare(scope)
            if (
                len(prepared["windows"]) != len(windows[a : a + 3])
                or prepared["preparation_rejected"]
            ):
                raise ValueError("book_scope_preparation_rejected")
            for w in prepared["windows"]:
                messages = [schema_message, *messages_for(w, prompt)]
                size = sum(len(m["content"].encode()) + 128 for m in messages)
                if size > settings.prompt_budget_bytes:
                    raise ValueError(f"prompt_budget_exceeded_lesson_{number}")
                max_prompt = max(max_prompt, size)
            for w in windows[a : a + 3]:
                max_payload = max(max_payload, window_bytes(w, pages))
            path = folder / f"bai-{number:02d}-nhom-{shard:02d}.json"
            scopes.append((path, scope))
            plans.append(
                {
                    "key": f"bai-{number:02d}-nhom-{shard:02d}",
                    "scope": path.relative_to(ROOT).as_posix(),
                    "lesson_number": number,
                    "lesson_title": title,
                }
            )
        print(
            f"Bai {number:02d}: PDF{start}-{end}, {len(windows)} windows prepared offline",
            flush=True,
        )
    total = sum(r.get("windows", 0) for r in chapters)
    plan = {
        "book": "Cấp cứu ngoại khoa – Chấn thương",
        "publication_year": 2006,
        "source_id": "SRC_ORTHO_EMERGENCY_001",
        "ocr_input": ocr_path.relative_to(ROOT).as_posix(),
        "source_sha256": ocr["source_sha256"],
        "lesson_order": "1 through 25; skip generation only for lessons 15 and 16",
        "chapters": chapters,
        "shards": plans,
        "recommended_max_calls": total * 2,
        "timeout_policy": {
            "response_seconds": None,
            "total_wait_seconds": None,
            "connect_seconds": 30,
        },
        "base_runs": [],
    }
    summary = {
        "lessons_total": 25,
        "lessons_scheduled": 23,
        "lessons_skipped": [15, 16],
        "windows": total,
        "shards": len(plans),
        "recommended_max_calls": total * 2,
        "source_coverage_missing_lines": 0,
        "max_window_payload_bytes": max_payload,
        "max_prompt_bytes": max_prompt,
        "configured_prompt_budget_bytes": settings.prompt_budget_bytes,
        "excluded_reasons": dict(Counter(r["reason"] for r in excluded)),
        "llm_calls": 0,
        "new_ocr_calls": 0,
        "neo4j_writes": 0,
        "body_pdf_pages": {"start": 8, "end": 168},
        "excluded_book_pages": [1, 2, 3, 4, 5, 6, 7, 169],
    }
    for path, value in scopes:
        write_json(path, value)
    write_json(plan_path, plan)
    write_json(audit_path / "summary.json", summary)
    write_json(audit_path / "chapter-index.json", chapters)
    write_json(audit_path / "source-coverage.json", coverage)
    write_json(audit_path / "excluded-lines.json", excluded)
    write_json(
        audit_path / "scope-hashes.json",
        {
            path.relative_to(ROOT).as_posix(): fingerprint(value)
            for path, value in scopes
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "book-2006-full-plan.json")
    parser.add_argument(
        "--audit",
        type=Path,
        default=ROOT / "data/knowledge-extraction/book-2006-full-preparation-20261102",
    )
    args = parser.parse_args()
    prepare_book(args.plan, args.audit)


if __name__ == "__main__":
    main()
