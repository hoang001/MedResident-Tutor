"""Materialize only manually selected, source-backed excerpts and figures."""
import io
import re
from collections import defaultdict
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from .io import DATA, read, sha, write
from .pmc import blocks_and_figures, media_url, prepare
from .contracts import validate_records

FIELDS = ("presentation", "investigations", "reference_diagnosis", "management", "outcome")


def excerpt(selector, blocks):
    selector = {"block": selector} if isinstance(selector, str) else selector
    block = blocks[selector["block"]]
    start, stop = 0, len(block["text"])
    if "start" in selector:
        if block["text"].count(selector["start"]) != 1:
            raise ValueError("start_marker_not_unique")
        start = block["text"].index(selector["start"])
    if "end_before" in selector:
        if block["text"].count(selector["end_before"]) != 1:
            raise ValueError("end_marker_not_unique")
        stop = block["text"].index(selector["end_before"])
    if stop <= start:
        raise ValueError("invalid_manual_excerpt_span")
    selected = block["text"][start:stop]
    return selected, {"block_id": block["block_id"], "locator": block["locator"], "section": block["section"],
                      "normalized_char_start": start, "normalized_char_end": stop, "excerpt": selected,
                      "normalization": "XML itertext joined; whitespace collapsed before offsets"}


def build_cases(fetcher):
    selections = read(DATA / "catalog/manual-selection.json")["cases"]
    cases, images, catalog = [], [], []
    for selection in selections:
        pmcid = selection["pmcid"]
        prepare(fetcher, pmcid)
        parsed = blocks_and_figures((DATA / "raw/pmc" / (pmcid + ".xml")).read_bytes())
        record = read(DATA / "raw/pmc" / (pmcid + "-record.json"))
        original = record["metadata"]
        source_id = "SRC_CASE_" + pmcid
        case_id = "CASE_" + pmcid + "_01"
        source = {"source_id": source_id, "data_kind": "published_clinical_case", "title": parsed["title"],
                  "authors": parsed["authors"], "year": int(parsed["publication_year"]) if parsed["publication_year"] else None,
                  "doi": original["doi"], "pmcid": pmcid, "dataset_version": None, "article_version": original["version"],
                  "original_url": "https://pmc.ncbi.nlm.nih.gov/articles/" + pmcid + "/",
                  "publisher_url": "https://doi.org/" + original["doi"],
                  "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                  "license_evidence": {"xml_locator": "/article/front/article-meta/permissions/license", "text": parsed["license_text"], "xml_sha256": parsed["xml_sha256"]},
                  "attribution_text": "; ".join(parsed["authors"]) + ". " + parsed["title"] + ". " + original["doi"] + ". CC BY 4.0. Source: NLM PMC official cloud. Unmodified figures; selected excerpts.",
                  "retrieval_date": record["retrieval"]["retrieval_date"], "access": "public_no_login",
                  "rights": {"download": True, "automated_download": True, "store_images": True, "adapt": True, "redistribute": True, "attribution_required": True, "noncommercial_only": False}}
        blocks = {b["block_id"]: b for b in parsed["blocks"]}
        case = {"case_id": case_id, "title": parsed["title"], "specialty": selection["specialty"], "topics": selection["topics"],
                "data_kind": "published_clinical_case", "patient_in_article": selection["patient_in_article"],
                "patient_group_id": case_id, "article_group_id": pmcid,
                "image_ids": [], "source_refs": {}, "language": "en", "translation": None,
                "extraction_method": "manual_excerpt_selection_no_LLM_no_OCR",
                "reference_diagnosis_scope": "diagnosis_reported_for_this_patient_not_general_answer_key",
                "source_variant_note": selection["source_variant_note"], "typicality": "not_validated_as_typical",
                "expert_verified": False, "split": "unassigned_review_only",
                "review_status": "source_checked_pending_clinical_expert_and_privacy_review"}
        for field in FIELDS:
            parts, refs = [], []
            for selector in selection["fields"].get(field, []):
                part, ref = excerpt(selector, blocks)
                parts.append(part)
                refs.append({**ref, "source_id": source_id, "xml_sha256": parsed["xml_sha256"]})
            case[field] = "\n\n".join(parts) if parts else None
            case["source_refs"][field] = refs
        figure_index = {f["figure_id"]: f for f in parsed["figures"]}
        for chosen in selection["figures"]:
            fig = figure_index[chosen["id"]]
            if fig["credit"] or re.search(r"reprinted|reproduced from|adapted from|courtesy of|with permission", fig["caption"], re.I):
                raise ValueError("separate_figure_rights_need_review")
            if len(fig["graphics"]) != 1:
                raise ValueError("ambiguous_multipanel_asset_keep_out")
            url = media_url(original, fig["graphics"][0])
            md5 = parse_qs(urlsplit(url).query).get("md5", [None])[0]
            body, audit = fetcher.get(url, maximum=15_000_000, expected_md5=md5)
            picture = Image.open(io.BytesIO(body))
            picture.load()
            image_id = "IMG_" + pmcid + "_" + chosen["id"]
            filename = urlsplit(url).path.rsplit("/", 1)[-1]
            path = DATA / "images/cases" / pmcid / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            image = {"image_id": image_id, "case_id": case_id, "study_id": None, "modality": chosen["modality"],
                     "body_region": chosen["body_region"], "view": chosen["view"],
                     "local_path": path.relative_to(DATA).as_posix(), "original_url": url,
                     "caption": fig["caption"], "annotation_refs": [], "source_id": source_id,
                     "sha256": sha(body), "width": picture.width, "height": picture.height,
                     "figure_id": chosen["id"], "figure_locator": fig["locator"],
                     "figure_credit_review": "no_separate_credit_found_in_JATS_figure_or_caption; article_CC_BY_applied",
                     "privacy_review": "pending_visual_review", "diagnosis_leakage_review": "caption discloses findings; burned-in text not erased",
                     "panels": "original_montage_preserved_not_split", "expert_verified": False,
                     "retrieval_date": audit["retrieval_date"]}
            images.append(image)
            case["image_ids"].append(image_id)
        cases.append(case)
        catalog.append(source)
        # Complete-case checkpoint. Individual successful requests are also cached.
        write(DATA / "processed/clinical-cases.json", cases)
        write(DATA / "processed/case-images.json", images)
        write(DATA / "catalog/case-sources.json", catalog)
        print("Clinical case completed:", case_id, len(case["image_ids"]), "figures", flush=True)
    write(DATA / "processed/authored-exercises.json", [])
    return cases, images, catalog


def validate():
    """Full local readback: exact excerpts, image hashes, unique IDs and grouping."""
    cases = read(DATA / "processed/clinical-cases.json")
    images = read(DATA / "processed/case-images.json") + read(DATA / "processed/dataset-images.json")
    studies = read(DATA / "processed/imaging-studies.json")
    sources = read(DATA / "catalog/case-sources.json") + [read(DATA / "catalog/graz-source.json")]
    for kind, rows in (("ClinicalCase", cases), ("MedicalImage", images), ("ImagingStudy", studies), ("Source", sources)):
        validate_records(kind, rows)
    for rows, key in ((cases, "case_id"), (images, "image_id"), (studies, "study_id"), (sources, "source_id")):
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError("duplicate_external_id:" + key)
    doi_groups = defaultdict(list)
    for s in sources:
        doi_groups[s["doi"].lower()].append(s["source_id"])
    if any(len(v) > 1 for v in doi_groups.values()):
        raise ValueError("duplicate_source_doi_needs_crosspublication_review")
    image_index, source_index = {i["image_id"]: i for i in images}, {s["source_id"]: s for s in sources}
    hashes = defaultdict(list)
    for image in images:
        body = (DATA / image["local_path"]).read_bytes()
        if sha(body) != image["sha256"] or image["source_id"] not in source_index:
            raise ValueError("image_hash_or_source_mismatch")
        picture = Image.open(io.BytesIO(body))
        picture.load()
        if picture.size != (image["width"], image["height"]):
            raise ValueError("image_dimensions_mismatch")
        hashes[sha(body)].append(image["image_id"])
    for case in cases:
        pmcid = case["article_group_id"]
        parsed = blocks_and_figures((DATA / "raw/pmc" / (pmcid + ".xml")).read_bytes())
        blocks = {b["block_id"]: b for b in parsed["blocks"]}
        figures = {f["figure_id"]: f for f in parsed["figures"]}
        for field in FIELDS:
            texts = []
            for ref in case["source_refs"][field]:
                block = blocks[ref["block_id"]]
                if (parsed["xml_sha256"] != ref["xml_sha256"] or block["locator"] != ref["locator"]
                        or block["text"][ref["normalized_char_start"]:ref["normalized_char_end"]] != ref["excerpt"]):
                    raise ValueError("manual_excerpt_not_exact_source")
                texts.append(ref["excerpt"])
            if case[field] != ("\n\n".join(texts) if texts else None):
                raise ValueError("case_field_not_exact_selected_excerpts")
        for image_id in case["image_ids"]:
            image = image_index[image_id]
            if image["case_id"] != case["case_id"] or image["caption"] != figures[image["figure_id"]]["caption"]:
                raise ValueError("figure_caption_case_mismatch")
    annotation_checks = 0
    for study in studies:
        for image_id in study["image_ids"]:
            image = image_index[image_id]
            row = image["source_row"]
            if (image["study_id"] != study["study_id"] or row["patient_id"] != study["original_study_id"]["patient_id"]
                    or row["study_number"] != study["original_study_id"]["study_number"]):
                raise ValueError("image_study_patient_group_mismatch")
            # Cross-check original YOLO normalized boxes against original VOC pixel boxes.
            # Rounding/origin conventions can differ by ~1 px; preserve both unchanged.
            yolo_path = DATA / next(p for p in image["annotation_refs"] if p.endswith(".txt"))
            yolo = [line.split() for line in yolo_path.read_text().splitlines() if line.strip()]
            if len(yolo) != len(image["annotations"]):
                raise ValueError("VOC_YOLO_object_count_mismatch")
            class_names = [line[2:].strip() for line in (DATA / "raw/graz/yolov5-meta.yaml").read_text().splitlines() if line.startswith("- ")]
            for obj, encoded in zip(image["annotations"], yolo):
                idx, x, y, w, h = map(float, encoded)
                if class_names[int(idx)] != obj["name"] or not all(0 <= v <= 1 for v in (x, y, w, h)):
                    raise ValueError("annotation_class_or_normalized_coordinates_mismatch")
                box = obj["bbox_original"]
                expected = [(x-w/2)*image["width"], (y-h/2)*image["height"], (x+w/2)*image["width"], (y+h/2)*image["height"]]
                if max(abs(a-b) for a, b in zip(expected, [box[k] for k in ("xmin", "ymin", "xmax", "ymax")])) > 2:
                    raise ValueError("VOC_YOLO_geometry_mismatch")
                annotation_checks += 1
    report = {"status": "automatic_source_integrity_checks_passed_not_expert_verification",
              "clinical_cases": len(cases), "clinical_case_figures": sum(i["case_id"] is not None for i in images),
              "imaging_studies": len(studies), "dataset_images": sum(i["study_id"] is not None for i in images),
              "cases_with_diagnosis": sum(bool(c["reference_diagnosis"]) for c in cases),
              "cases_with_management": sum(bool(c["management"]) for c in cases),
              "cases_with_outcome": sum(bool(c["outcome"]) for c in cases),
              "case_specialties": {k: sum(c["specialty"] == k for c in cases) for k in {c["specialty"] for c in cases}},
              "duplicate_image_hash_groups": [v for v in hashes.values() if len(v) > 1],
              "VOC_YOLO_object_geometry_checks": annotation_checks,
              "authored_exercises": 0, "llm_calls": 0, "expert_verified": False,
              "database_imports": 0, "training_or_locked_test_changes": 0}
    write(DATA / "audit/validation.json", report)
    return report
