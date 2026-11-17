"""Page-specific, visually confirmed OCR patches. Never edits original OCR/PDF."""

import re
from pathlib import Path

from document_toolkit.common import fingerprint
from knowledge_pipeline.pipeline import digest


def protected_markers(text):
    return re.findall(
        r"\d+(?:[.,]\d+)?|[<>≤≥=]|\b(?:không|chưa|nếu|khi|trừ|mg|ml|cm|mm|UI)\b",
        text,
        re.IGNORECASE,
    )


def correct_page(raw_text, patches, *, source_id, page, ocr_sha256, pdf_sha256, root):
    applicable = sorted(
        [p for p in patches if p["source_id"] == source_id and p["pdf_page"] == page],
        key=lambda p: p["raw_start"],
    )
    cursor, corrected, segments, applied = 0, "", [], []

    def add(start, end, text, patch_id=None):
        nonlocal corrected
        cstart = len(corrected)
        corrected += text
        segments.append(
            {
                "raw_start": start,
                "raw_end": end,
                "corrected_start": cstart,
                "corrected_end": len(corrected),
                "patch_id": patch_id,
            }
        )

    for patch in applicable:
        start, end = patch["raw_start"], patch["raw_end"]
        if (
            start < cursor
            or end <= start
            or raw_text[start:end] != patch["before"]
            or patch["ocr_sha256"] != ocr_sha256
            or patch["source_pdf_sha256"] != pdf_sha256
        ):
            raise ValueError("ocr_patch_does_not_match_immutable_source")
        if patch.get("decision") != "confirmed_visual_transcription":
            raise ValueError("unconfirmed_ocr_patch")
        proof = (Path(root) / patch["image_path"]).resolve()
        if (
            not proof.is_relative_to(Path(root).resolve())
            or not proof.is_file()
            or digest(proof) != patch["image_sha256"]
        ):
            raise ValueError("ocr_patch_image_proof_missing_or_changed")
        if protected_markers(patch["before"]) != protected_markers(patch["after"]):
            raise ValueError("ocr_patch_changes_numeric_or_negation_markers")
        if patch.get("kind") != "ocr_character_or_word":
            raise ValueError("medical_knowledge_rewrite_not_allowed")
        add(cursor, start, raw_text[cursor:start])
        add(start, end, patch["after"], patch["id"])
        applied.append(patch["id"])
        cursor = end
    add(cursor, len(raw_text), raw_text[cursor:])
    return {
        "raw_text": raw_text,
        "corrected_text": corrected,
        "segments": segments,
        "patch_ids": applied,
        "revision": fingerprint([raw_text, applicable]),
        "expert_review": "unverified",
    }


def trace_raw(correction, start, end):
    ranges, patch_ids = [], []
    for s in correction["segments"]:
        lo, hi = max(start, s["corrected_start"]), min(end, s["corrected_end"])
        if lo >= hi:
            continue
        if s["patch_id"]:
            ranges.append((s["raw_start"], s["raw_end"]))
            patch_ids.append(s["patch_id"])
        else:
            ranges.append(
                (
                    s["raw_start"] + lo - s["corrected_start"],
                    s["raw_start"] + hi - s["corrected_start"],
                )
            )
    if not ranges:
        raise ValueError("corrected_span_has_no_raw_trace")
    raw_start, raw_end = min(r[0] for r in ranges), max(r[1] for r in ranges)
    return {
        "raw_char_start": raw_start,
        "raw_char_end": raw_end,
        "raw_text": correction["raw_text"][raw_start:raw_end],
        "corrected_text": correction["corrected_text"][start:end],
        "patch_ids": sorted(set(patch_ids)),
        "correction_revision": correction["revision"],
    }
