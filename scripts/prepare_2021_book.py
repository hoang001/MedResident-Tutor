"""Offline scope for all available 2021 textbook lessons, objectives and questions.

No LLM/OCR/Neo4j calls. Missing source openings are reported, never fabricated.
"""

import copy
import json
import re
import unicodedata
from collections import Counter

from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import Settings
from knowledge_pipeline.kg_v2.contracts import MEDICAL, RELATIONS, schemas
from knowledge_pipeline.kg_v2.draft_run import DRAFT_INSTRUCTION, messages_for
from knowledge_pipeline.kg_v2.pipeline import HERE, ROOT, prepare
from scripts.prepare_2006_book import (
    ImageText,
    heading_depth,
    normalized,
    selectors_for,
    window_bytes,
)

CHAPTERS = [
    (1, "Điều trị bảo tồn gãy xương chi", 8),
    (2, "Điều trị phẫu thuật gãy xương bằng kết hợp xương bên trong", 23),
    (3, "Điều trị phẫu thuật gãy xương bằng khung cố định ngoài", 40),
    (4, "Hội chứng chèn ép khoang cấp tính", 55),
    (5, "Gãy xương hở", 66),
    (6, "Điều trị vết thương khớp", 79),
    (7, "Vết thương phần mềm", 91),
    (8, "Uốn ván", 102),
    (9, "Hoại thư sinh hơi", 111),
    (10, "Điều trị bỏng", 117),
    (11, "Đại cương u xương", 130),
    (12, "Đại cương dị tật chi trên", 149),
    (13, "Đại cương dị tật chi dưới", 166),
    (14, "Viêm xương tủy", 181),
    (15, "Điều trị chấn thương cột sống cổ thấp", 195),
    (16, "Chẩn đoán và điều trị chấn thương cột sống cổ cao", 213),
    (17, "Điều trị chấn thương cột sống ngực thắt lưng", 227),
    (18, "Điều trị gãy xương đòn", 245),
    (19, "Điều trị trật khớp vai", 254),
    (20, "Điều trị gãy cổ xương cánh tay", 270),
    (21, "Điều trị gãy thân xương cánh tay", 281),
    (22, "Gãy trên lồi cầu xương cánh tay ở trẻ em", 297),
    (23, "Điều trị trật khớp khuỷu", 312),
    (24, "Điều trị gãy mỏm khuỷu", 325),
    (25, "Điều trị gãy hai xương cẳng tay", 338),
    (26, "Điều trị gãy đầu dưới xương quay", 354),
    (27, "Vết thương bàn tay", 369),
    (28, "Điều trị nhiễm trùng bàn tay", 382),
    (29, "Điều trị gãy xương chậu", 405),
    (30, "Điều trị trật khớp háng", 423),
    (31, "Điều trị gãy cổ xương đùi", 441),
    (32, "Điều trị gãy thân xương đùi", 459),
    (33, "Điều trị trật khớp gối cấp tính", 475),
    (34, "Điều trị gãy xương bánh chè", 490),
    (35, "Điều trị gãy mâm chày", 504),
    (36, "Điều trị gãy hai xương cẳng chân", 516),
]
MISSING_OPENINGS = {10, 14, 16, 18}


def plain(text):
    text = unicodedata.normalize("NFD", text).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


class LayoutText(ImageText):
    def __init__(self):
        super().__init__()
        self.layout = set()

    def handle_endtag(self, tag):
        if tag == "div" and self.divs:
            div = self.divs[-1]
            if div["label"] in {"Page-Header", "Page-Footer"}:
                self.layout.add(normalized(" ".join(div["text"])))
                self.layout.update(normalized(t) for t in div["text"] if t.strip())
        super().handle_endtag(tag)


def marker(text):
    value = plain(text).strip()
    if len(value) > 85:
        return None
    if "tieu hoc tap" in value:
        return "learning_objective"
    if "noi dung hoc tap" in value:
        return "medical_text"
    if value.startswith("cau hoi") and text.isupper() and not re.search(r"\d", value):
        return "question"
    if value.startswith("tai lieu tham"):
        return "references"
    if value in {"dap an", "goi y dap an"}:
        return "answer"
    return None


def lesson_context(number, start, pages):
    lines = pages[start]["text"].splitlines()
    if number not in MISSING_OPENINGS:
        assert re.fullmatch(rf"Bài\s+{number}", lines[0], re.IGNORECASE)
        refs = [(start, 0)]
        for i, line in enumerate(lines[1:], 1):
            if line.isupper() and marker(line) is None:
                refs.append((start, i))
            else:
                break
        objective = next(
            (i for i, t in enumerate(lines) if marker(t) == "learning_objective"), None
        )
        if objective is None:
            raise ValueError(f"objective_boundary_not_found_lesson_{number}")
        return refs, set(range(objective)), False
    # The actual lesson opening is absent from the PDF. The TOC provides only a
    # sourced subject heading; it must never substitute missing medical content.
    for page in [5, 6, 7]:
        for i, text in enumerate(pages[page]["text"].splitlines()):
            if re.match(rf"^Bài\s+{number}\.", text, re.IGNORECASE):
                return [(page, i)], set(), True
    raise ValueError("missing_lesson_toc_context")


def units_for(number, start, end, pages):
    ctx, opening, gap = lesson_context(number, start, pages)
    context_set = set(ctx)
    units, excluded, retained, stack = [], [], set(), []
    mode = "medical_text"
    current = None

    def close():
        nonlocal current
        if current and current["lines"]:
            units.append(current)
        current = None

    for page in range(start, end + 1):
        row = pages[page]
        parser = LayoutText()
        parser.feed(row.get("html", ""))
        lines = row["text"].splitlines()
        page_rows = []
        for i, text in enumerate(lines):
            ref = (page, i)
            reason = None
            norm = normalized(text)
            next_mode = marker(text)
            if ref in context_set:
                reason = "chapter_heading_kept_as_context"
            elif page == start and i in opening:
                reason = "opening_author_credit"
            elif not text.strip():
                reason = "empty_line"
            elif norm in parser.layout:
                reason = "ocr_page_header_footer"
            elif i >= len(lines) - 2 and re.fullmatch(r"\d{1,3}", text.strip()):
                reason = "trailing_printed_page_number"
            elif re.match(r"^Hình\s+\d", text, re.IGNORECASE):
                reason = "numbered_figure_caption"
            elif norm in parser.descriptions:
                reason = "ocr_image_description_not_book_prose"
            if reason:
                excluded.append(
                    {
                        "lesson_number": number,
                        "pdf_page": page,
                        "line": i,
                        "text": text,
                        "reason": reason,
                    }
                )
                continue
            if next_mode:
                # Record the role in source order below. Do not close/reset the
                # previous page's section before processing this page's prose.
                mode = next_mode
                if mode in {"references", "medical_text"}:
                    reason = (
                        "bibliography_heading"
                        if mode == "references"
                        else "body_layout_heading"
                    )
                    excluded.append(
                        {
                            "lesson_number": number,
                            "pdf_page": page,
                            "line": i,
                            "text": text,
                            "reason": reason,
                        }
                    )
                    continue
            if mode == "references":
                excluded.append(
                    {
                        "lesson_number": number,
                        "pdf_page": page,
                        "line": i,
                        "text": text,
                        "reason": "bibliography_not_medical_prose",
                    }
                )
                continue
            page_rows.append((ref, mode))
            retained.add(ref)
        # Process by role so objectives/questions on a table page remain intact
        # and do not become table captions or generic theory.
        tables = bool(re.search(r"<table\b", row.get("html", ""), re.IGNORECASE))
        table_rows = (
            [ref for ref, role in page_rows if role == "medical_text"] if tables else []
        )
        table_done = False
        for ref, role in page_rows:
            text = lines[ref[1]]
            if ref in table_rows:
                if not table_done:
                    close()
                    units.append(
                        {
                            "lines": table_rows,
                            "parents": [h for _, h in stack],
                            "role": "table",
                            "heading": f"Bảng và ngữ cảnh PDF{page}",
                        }
                    )
                    table_done = True
                depth = heading_depth(text)
                if depth is not None:
                    stack = [(d, h) for d, h in stack if d < depth] + [(depth, ref)]
                continue
            if role in {"learning_objective", "question", "answer"}:
                if current is None or current["role"] != role:
                    close()
                    stack = []
                    current = {
                        "lines": [],
                        "parents": [],
                        "role": role,
                        "heading": text,
                    }
                # Keep the entire real question section, including cases/options.
                current["lines"].append(ref)
                continue
            depth = heading_depth(text)
            if current and current["role"] != "medical_text":
                close()
                stack = []
            if depth is not None:
                close()
                stack = [(d, h) for d, h in stack if d < depth]
                current = {
                    "lines": [],
                    "parents": [h for _, h in stack],
                    "role": "medical_text",
                    "heading": text,
                }
                stack.append((depth, ref))
            if current is None:
                current = {
                    "lines": [],
                    "parents": [h for _, h in stack],
                    "role": "medical_text",
                    "heading": text[:110],
                }
            current["lines"].append(ref)
    close()
    for unit in units:
        if unit["role"] != "medical_text":
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
    return ctx, gap, units, excluded, retained


def window_for(number, title, ctx, units, pages, index):
    selectors = selectors_for(ctx, "chapter_context", pages)
    if units:
        selectors += selectors_for(units[0]["parents"], "medical_text", pages)
    for unit in units:
        selectors += selectors_for(unit["lines"], unit["role"], pages)
    return {
        "key": f"2021-bai-{number:02d}-phan-{index:03d}",
        "section_id": f"book-2021-bai-{number:02d}-phan-{index:03d}",
        "title": f"Bài {number}. {title} — {units[0]['heading']}",
        "selectors": selectors,
    }


def structured(window):
    # The current line-structure helper repeats table_html on every text line.
    # Use its existing unstructured scope mode for a dedicated table window to
    # retain the whole layout once without exceeding the prompt budget.
    return not any(s["role"] == "table" for s in window["selectors"])


def main():
    plan_path = HERE / "book-2021-all-lessons-plan.json"
    audit = ROOT / "data/knowledge-extraction/book-2021-preparation-20261102"
    scopes_folder = HERE / "book-2021-all-lessons-scopes"
    if plan_path.exists() or scopes_folder.exists():
        raise ValueError("new_2021_plan_required_no_overwrite")
    ocr_path = ROOT / "data/graduate/DVC.005844.json"
    ocr = read_json(ocr_path)
    pages = {r["page_start"]: r for r in ocr["sections"]}
    settings = Settings.from_env()
    base = read_json(HERE / "shoulder-scope-20261030.json")
    base["documents"] = [
        copy.deepcopy(
            next(b for b in base["documents"] if b["publication_year"] == 2021)
        )
    ]
    base.pop("ocr_patches", None)
    base.pop("ocr_issues", None)
    base["documents"][0]["verified_printed_labels"] = {}
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
    scopes = []
    shards = []
    chapters = []
    all_excluded = []
    coverage = []
    max_prompt = 0
    max_payload = 0

    def scope_for(window, section):
        scope = copy.deepcopy(base)
        scope["structured_context"] = structured(window)
        scope["documents"][0]["survey_sections"] = [section]
        scope["documents"][0]["windows"] = [window]
        return scope

    for offset, (number, title, start) in enumerate(CHAPTERS):
        end = CHAPTERS[offset + 1][2] - 1 if offset + 1 < len(CHAPTERS) else 531
        ctx, gap, units, excluded, kept = units_for(number, start, end, pages)
        section = {
            "key": f"book-2021-bai-{number:02d}",
            "original_title": f"Bài {number}. {title}",
            "parent_key": None,
            "pdf_pages": {"start": start, "end": end},
            "printed_pages": None,
            "boundary_status": "opening_missing_visual_pdf_and_toc_subject_context"
            if gap
            else "ocr_numbered_lesson_heading_to_next_lesson",
        }
        groups = []
        chunk = []
        for unit in units:
            root = unit["parents"][0] if unit["parents"] else unit["lines"][0]
            previous = (
                (
                    chunk[0]["parents"][0]
                    if chunk[0]["parents"]
                    else chunk[0]["lines"][0]
                )
                if chunk
                else None
            )
            special = unit["role"] in {
                "learning_objective",
                "question",
                "answer",
                "table",
            }
            previous_special = chunk and chunk[0]["role"] in {
                "learning_objective",
                "question",
                "answer",
                "table",
            }
            w = window_for(number, title, ctx, chunk + [unit], pages, len(groups) + 1)
            if chunk and (
                len(chunk) >= 3
                or root != previous
                or special
                or previous_special
                or window_bytes(w, pages) > 4500
            ):
                groups.append(chunk)
                chunk = []
            chunk.append(unit)
        if chunk:
            groups.append(chunk)
        refined = []
        pending = list(groups)
        while pending:
            group = pending.pop(0)
            w = window_for(number, title, ctx, group, pages, len(refined) + 1)
            prepared = prepare(scope_for(w, section))
            fits = (
                len(prepared["windows"]) == 1 and not prepared["preparation_rejected"]
            )
            if fits:
                messages = [
                    schema_message,
                    *messages_for(prepared["windows"][0], prompt),
                ]
                size = sum(len(m["content"].encode()) + 128 for m in messages)
                fits = size <= settings.prompt_budget_bytes
            if not fits:
                if len(group) == 1:
                    write_json(
                        audit / "oversize-unit.json",
                        {"lesson_number": number, "unit": group[0]},
                    )
                    raise ValueError(f"atomic_unit_too_large_lesson_{number}")
                mid = len(group) // 2
                pending[0:0] = [group[:mid], group[mid:]]
                continue
            max_prompt = max(max_prompt, size)
            max_payload = max(max_payload, window_bytes(w, pages))
            refined.append(group)
        windows = [
            window_for(number, title, ctx, group, pages, i + 1)
            for i, group in enumerate(refined)
        ]
        covered = {r for group in refined for unit in group for r in unit["lines"]}
        assert covered == kept
        # Three windows fit the existing six-attempt shard guard. Table windows
        # have their own unstructured shard, never mixed with structured windows.
        batches = []
        chunk = []
        for w in windows:
            if chunk and (
                len(chunk) >= 3 or not structured(w) or not structured(chunk[0])
            ):
                batches.append(chunk)
                chunk = []
            chunk.append(w)
        if chunk:
            batches.append(chunk)
        for i, batch in enumerate(batches, 1):
            scope = scope_for(batch[0], section)
            scope["documents"][0]["windows"] = batch
            prepared = prepare(scope)
            assert (
                len(prepared["windows"]) == len(batch)
                and not prepared["preparation_rejected"]
            )
            path = scopes_folder / f"bai-{number:02d}-nhom-{i:02d}.json"
            scopes.append((path, scope))
            shards.append(
                {
                    "key": f"bai-{number:02d}-nhom-{i:02d}",
                    "scope": path.relative_to(ROOT).as_posix(),
                    "lesson_number": number,
                    "lesson_title": title,
                }
            )
        counts = Counter(unit["role"] for unit in units)
        chapters.append(
            {
                "lesson_number": number,
                "title": title,
                "pdf_pages": {"start": start, "end": end},
                "source_opening_missing": gap,
                "context_from_toc": gap,
                "generation_status": "scheduled",
                "windows": len(windows),
                "shards": len(batches),
                "objective_units": counts["learning_objective"],
                "question_units": counts["question"],
                "answer_units": counts["answer"],
                "partial_earlier_trial": number in {5, 19},
            }
        )
        coverage.append(
            {
                "lesson_number": number,
                "retained_lines": len(kept),
                "covered_lines": len(covered),
                "missing_selected_source_lines": [],
                "table_pages": [
                    p
                    for p in range(start, end + 1)
                    if re.search(r"<table\b", pages[p].get("html", ""), re.IGNORECASE)
                ],
            }
        )
        all_excluded.extend(excluded)
        print(
            f"Bai {number:02d}: PDF{start}-{end}, {len(windows)} windows, objectives={counts['learning_objective']}, questions={counts['question']}, missing_opening={gap}",
            flush=True,
        )
    total = sum(r["windows"] for r in chapters)
    gaps = [
        {
            "lesson_number": number,
            "title": title,
            "first_available_pdf_page": start,
            "issue": "Opening/initial medical content absent in the available PDF; first available page is a continuation. TOC used for subject context only. No missing objectives/content synthesized.",
        }
        for number, title, start in CHAPTERS
        if number in MISSING_OPENINGS
    ]
    plan = {
        "book": "Bệnh học ngoại khoa – Chấn thương chỉnh hình",
        "publication_year": 2021,
        "source_id": base["documents"][0]["source_id"],
        "ocr_input": ocr_path.relative_to(ROOT).as_posix(),
        "source_sha256": ocr["source_sha256"],
        "chapters": chapters,
        "shards": shards,
        "base_runs": [],
        "recommended_max_calls": 2 * total,
        "source_gaps": gaps,
        "lessons_skipped": [],
        "timeout_policy": {
            "response_seconds": None,
            "total_wait_seconds": None,
            "connect_seconds": 30,
        },
    }
    summary = {
        "lessons_total": 36,
        "lessons_scheduled": 36,
        "lessons_skipped": [],
        "windows": total,
        "shards": len(shards),
        "recommended_max_calls": 2 * total,
        "source_openings_missing": sorted(MISSING_OPENINGS),
        "source_coverage_missing_selected_lines": 0,
        "objective_units": sum(r["objective_units"] for r in chapters),
        "question_units": sum(r["question_units"] for r in chapters),
        "max_prompt_bytes": max_prompt,
        "prompt_budget_bytes": settings.prompt_budget_bytes,
        "max_payload_bytes": max_payload,
        "excluded_reasons": dict(Counter(r["reason"] for r in all_excluded)),
        "llm_calls": 0,
        "new_ocr_calls": 0,
        "neo4j_writes": 0,
    }
    for path, scope in scopes:
        write_json(path, scope)
    write_json(plan_path, plan)
    for name, value in [
        ("summary", summary),
        ("chapter-index", chapters),
        ("source-gaps", gaps),
        ("source-coverage", coverage),
        ("excluded-lines", all_excluded),
        (
            "scope-hashes",
            {p.relative_to(ROOT).as_posix(): fingerprint(s) for p, s in scopes},
        ),
    ]:
        write_json(audit / (name + ".json"), value)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
