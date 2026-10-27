"""Validate only processed records, catalog and the supplied integration manifest.

No model/training/prepared data is opened. Strings are preserved verbatim.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CaseError(ValueError):
    pass


class CaseConflict(CaseError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CaseError(message)


def within(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and bool(relative.strip()), "Empty source path")
    require(not Path(relative).is_absolute(), "Expected a repository-relative path")
    target = (root / relative).resolve()
    require(target.is_relative_to(root.resolve()), "Source path escapes repository root")
    return target


def read_json(path: Path) -> Any:
    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj, f"Duplicate JSON key: {key}")
            obj[key] = value
        return obj

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs)


def records(path: Path, key: str) -> dict[str, dict]:
    found = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            external_id = row.get(key)
            require(isinstance(external_id, str) and bool(external_id.strip()), f"Invalid {key}")
            require(external_id not in found, f"Duplicate {key}: {external_id}")
            found[external_id] = row
    return found


def unique_ids(values: Any, label: str) -> list[str]:
    require(isinstance(values, list) and bool(values), f"Empty/invalid {label}")
    require(
        all(isinstance(v, str) and v.strip() and len(v) <= 255 for v in values), f"Invalid {label}"
    )
    require(len(values) == len(set(values)), f"Duplicate {label}")
    return values


def pages(value: dict, label: str) -> tuple[int, int]:
    start, end = value.get("start"), value.get("end")
    require(
        type(start) is int and type(end) is int and 1 <= start <= end, f"Invalid {label} page range"
    )
    return start, end


@dataclass(frozen=True)
class CaseInput:
    manifest: dict
    catalog: dict
    question: dict
    rubric: dict
    units: list[dict]
    pdf: Path
    sha256: str
    manifest_path: str

    @property
    def storage_key(self) -> str:
        # Safe stable path under FILE_STORAGE_PATH; never a source repo-relative path.
        return f"integration/{self.catalog['source_id']}/{self.sha256}.pdf"


def load_case(repo_root: Path, manifest_path: Path) -> CaseInput:
    root = repo_root.resolve()
    manifest_path = (root / manifest_path).resolve()
    require(manifest_path.is_relative_to(root), "Manifest must be inside repository root")
    m = read_json(manifest_path)
    require(m.get("purpose") == "technical_integration_trial", "Not a technical case manifest")
    require(m.get("manifest_version") == "1.0.0", "Unsupported manifest version")
    qs = records(root / "data/processed/qa_items.jsonl", "question_id")
    rs = records(root / "data/processed/rubrics.jsonl", "rubric_id")
    us = records(root / "data/processed/source_units.jsonl", "source_unit_id")
    cs = records(root / "data/sources/source_catalog.jsonl", "source_id")
    try:
        q, rubric, catalog = qs[m["question_id"]], rs[m["rubric_id"]], cs[m["source_id"]]
        unit_ids = unique_ids(m["source_unit_ids"], "source_unit_ids")
        units = [us[key] for key in unit_ids]
    except KeyError as exc:
        raise CaseError(f"Missing reference: {exc.args[0]}") from exc
    require(
        q["rubric_id"] == rubric["rubric_id"] and rubric["question_id"] == q["question_id"],
        "Question/rubric mismatch",
    )
    require(q["question_type"] == "recognition", "Unsupported dataset question_type mapping")
    for row in (q, rubric, *units):
        require(row.get("schema_version") == "1.0.0", "Unsupported dataset schema version")
    for field in ("course_id", "topic_id"):
        require(
            q.get(field) == rubric.get(field) and bool(q.get(field)),
            f"Question/rubric {field} mismatch",
        )
    for field in (
        "scoring_rule",
        "validation_status",
        "expert_review_required",
        "expert_review_reason",
    ):
        require(field in rubric, f"Missing rubric field: {field}")
    require(
        all(type(row.get("expert_review_required")) is bool for row in (q, rubric)),
        "Invalid expert review flag",
    )
    require(all(u.get("topic_id") == q["topic_id"] for u in units), "Unit topic mismatch")
    require(isinstance(q["question"], str) and bool(q["question"].strip()), "Empty question")
    criteria = rubric["criteria"]
    require(isinstance(criteria, list) and bool(criteria), "No criteria")
    criterion_ids = unique_ids([c["criterion_id"] for c in criteria], "criterion_ids")
    require(
        unique_ids(m["criterion_ids"], "manifest criterion_ids") == criterion_ids,
        "Manifest criterion order/IDs differ from rubric",
    )
    expected_units = set()
    for c in criteria:
        score = c["max_score"]
        require(
            type(score) in (int, float) and math.isfinite(score) and score > 0,
            "Invalid criterion max_score",
        )
        require(
            isinstance(c["description"], str) and bool(c["description"].strip()),
            "Empty criterion description",
        )
        expected_units.update(unique_ids(c["required_source_unit_ids"], "criterion sources"))
        for field in ("acceptable_variants", "common_incorrect_claims"):
            require(
                isinstance(c[field], list) and all(isinstance(s, str) for s in c[field]),
                f"Invalid {field}",
            )
    maximum = rubric["max_score"]
    require(
        type(maximum) in (int, float) and math.isfinite(maximum) and maximum > 0,
        "Invalid rubric max_score",
    )
    require(
        math.isclose(sum(c["max_score"] for c in criteria), maximum, abs_tol=1e-9, rel_tol=0),
        "Criterion total differs from rubric max_score",
    )
    require(
        expected_units == set(unit_ids) == set(unique_ids(q["source_unit_ids"], "QA sources")),
        "Evidence references differ between question/rubric/manifest",
    )
    require(all(u["source_id"] == catalog["source_id"] for u in units), "Source mismatch")
    require(
        all(isinstance(u["content"], str) and u["content"].strip() for u in units),
        "Empty evidence content",
    )
    require(re.fullmatch(r"SRC_[A-Z0-9_]+", catalog["source_id"]) is not None, "Unsafe source_id")
    locator = m["locator"]
    start, end = pages(locator["pdf_pages"], "PDF")
    require(locator["pdf_pages"].get("numbering") == "one_based", "PDF pages must be one-based")
    if locator.get("printed_pages") is not None:
        pages(locator["printed_pages"], "printed")
    count = m["source_document"]["pdf_page_count"]
    require(type(count) is int and end <= count, "PDF locator exceeds page count")
    require(count == catalog["file_scope"]["pdf_page_count"], "Catalog/page count mismatch")
    require(
        any(
            s["pdf_page_start"] <= start <= end <= s["pdf_page_end"]
            for s in catalog["registered_scopes"]
        ),
        "Locator outside catalog scope",
    )
    verification = m["evidence_verification"]
    require(verification["status"] == "compared_with_original_pdf", "Evidence not compared")
    entries = verification["criterion_evidence"]
    require(len(entries) == len(criteria), "Incomplete criterion verification")
    for c, entry in zip(criteria, entries, strict=True):
        require(
            entry["criterion_id"] == c["criterion_id"]
            and entry["source_unit_ids"] == c["required_source_unit_ids"]
            and entry["support"] == "direct",
            "Criterion verification mismatch",
        )
        require(start <= entry["pdf_page"] <= end, "Verified page outside locator")
        if locator.get("printed_pages") is not None:
            printed_start, printed_end = pages(locator["printed_pages"], "printed")
            require(
                printed_start <= entry["printed_page"] <= printed_end,
                "Verified printed page outside locator",
            )
    # A single locator applies to every listed unit; reject broader manifests for now.
    require(
        all(
            u["chapter"] == locator["chapter"] and u["section"] == locator["section"] for u in units
        ),
        "Units require different locators",
    )
    flags = m["existing_dataset_flags"]
    for label, row in (("question", q), ("rubric", rubric)):
        require(all(row[k] == v for k, v in flags[label].items()), "Stale review flags")
    require(
        all(all(u[k] == v for k, v in flags["source_unit"].items()) for u in units),
        "Stale source review flags",
    )
    pdf = within(root, m["source_document"]["repo_relative_path"])
    require(pdf.is_file() and pdf.name == catalog["file_name"], "PDF missing/name mismatch")
    sha = m["source_document"]["sha256"]
    require(
        isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha) is not None, "Invalid SHA-256"
    )
    require(digest(pdf) == sha, "PDF SHA-256 mismatch")
    with pdf.open("rb") as stream:
        require(stream.read(5) == b"%PDF-", "Not a PDF")
    return CaseInput(
        m, catalog, q, rubric, units, pdf, sha, manifest_path.relative_to(root).as_posix()
    )
