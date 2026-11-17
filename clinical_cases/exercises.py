"""Manual authoring adapter: bilingual exercises, byte-identical learner images, evidence packets."""
import hashlib
import html
import json
import shutil
from pathlib import Path

from PIL import Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .build import validate
from .io import DATA, read, sha, write
from .pmc import blocks_and_figures

OUT = DATA / "exercises"
PREFIX = "CLINICAL_DEMO_V1_"


def stable(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def learner_asset(exercise_id, image, order):
    asset_id = stable(exercise_id + ":" + image["image_id"])
    original = DATA / image["local_path"]
    suffix = original.suffix.lower()
    path = OUT / "assets" / (asset_id + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, path)
    if sha(path.read_bytes()) != image["sha256"]:
        raise ValueError("learner_copy_changed_original_pixels")
    with Image.open(path) as pic:
        if pic.size != (image["width"], image["height"]):
            raise ValueError("learner_image_geometry_changed")
    return {"asset_id": asset_id, "storage_key": "clinical-exercises/" + path.name,
            "bundle_path": path.relative_to(OUT).as_posix(), "sha256": image["sha256"],
            "width": image["width"], "height": image["height"],
            "mime_type": "image/png" if suffix == ".png" else "image/jpeg",
            "alt": f"Ảnh {order} của bài tập", "source_image_id": image["image_id"],
            "transformation": {"operation": "byte_identical_copy_with_opaque_filename", "pixel_edits": False,
                               "geometry": "identity", "annotations_transformed": False},
            "privacy_review": "selected_original_visually_screened_no_obvious_identifiers; not_expert_certified"}


def packet(exercise_id, source, evidence):
    """A real compiled PDF, clearly distinguished from original article page numbers."""
    path = OUT / "packets" / (exercise_id + ".pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    font = Path("C:/Windows/Fonts/arial.ttf")
    if not font.exists():
        font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    name = "EvidenceFont" if font.exists() else "Helvetica"
    if name == "EvidenceFont" and name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(font)))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = name
    parts = [Paragraph(html.escape("Compiled evidence packet: " + exercise_id), styles["Heading1"]),
             Paragraph("This packet was compiled by the project. Its PDF page numbers are NOT original article pages. XML/CSV/VOC locators below identify the original source. No expert approval is claimed.", styles["BodyText"]), Spacer(1, 12)]
    for item in evidence:
        parts += [Paragraph(html.escape(item["source_unit_id"]), styles["Heading2"]),
                  Paragraph(html.escape(item["content_en"]), styles["BodyText"]),
                  Paragraph(html.escape(json.dumps(item["source_ref"], ensure_ascii=False)), styles["BodyText"]), Spacer(1, 12)]
    parts += [Paragraph(html.escape(source["attribution_text"]), styles["BodyText"])]
    SimpleDocTemplate(str(path), invariant=1).build(parts)
    from pypdf import PdfReader
    reader = PdfReader(path)
    combined = " ".join((p.extract_text() or "") for p in reader.pages)
    if not all(item["source_unit_id"] in combined for item in evidence):
        raise ValueError("compiled_pdf_evidence_missing")
    return {"path": path.relative_to(OUT).as_posix(), "sha256": sha(path.read_bytes()), "pages": len(reader.pages),
            "page_basis": "compiled_packet_not_original_article"}


def build():
    validate()
    spec = read(OUT / "authoring.json")
    cases = {c["case_id"]: c for c in read(DATA / "processed/clinical-cases.json")}
    images = {i["image_id"]: i for i in read(DATA / "processed/case-images.json") + read(DATA / "processed/dataset-images.json")}
    sources = {s["source_id"]: s for s in read(DATA / "catalog/sources.json")}
    studies = read(DATA / "processed/imaging-studies.json")
    kg_path = OUT / "kg-readonly-candidates.json"
    kg = {n["id"]: n for n in read(kg_path)} if kg_path.exists() else {}
    rows = []
    for selected in spec["case_selections"]:
        case = cases[selected["case_id"]]
        exercise_id = PREFIX + selected["key"]
        source_id = case["source_refs"]["presentation"][0]["source_id"]
        source = sources[source_id]
        blocks = blocks_and_figures((DATA / "raw/pmc" / (case["article_group_id"] + ".xml")).read_bytes())["blocks"]
        block = next(b for b in blocks if b["block_id"] == selected["presentation_block"])
        presentation_en = block["text"]
        if selected.get("presentation_end_before"):
            presentation_en = presentation_en[:presentation_en.index(selected["presentation_end_before"])].strip()
        attached = [images[i] for i in case["image_ids"] if images[i]["figure_id"] in selected["figures"]]
        assets = [learner_asset(exercise_id, image, i+1) for i, image in enumerate(attached)]
        criteria, evidence = [], []
        for i, criterion in enumerate(selected["criteria"], 1):
            ref = next(r for r in case["source_refs"][criterion["evidence_field"]] if criterion["evidence_contains"] in r["excerpt"])
            cid, sid = exercise_id + f"_C{i:02d}", exercise_id + f"_SU{i:02d}"
            evidence.append({"source_unit_id": sid, "content_en": ref["excerpt"], "source_ref": ref,
                             "description_origin": "published_case_excerpt", "source_id": source_id})
            criteria.append({"criterion_id": cid, "description": criterion["answer_vi"], "max_score": 1.0,
                             "reference_answer_en": criterion["answer_en"], "reference_answer_vi": criterion["answer_vi"],
                             "acceptable_variants": criterion["variants"], "common_incorrect_claims": [],
                             "required_source_unit_ids": [sid], "kg_links": [kg[k] for k in criterion["kg_ids"] if k in kg]})
        payload = {"exercise_id": exercise_id, "title": "Ca bệnh " + selected["key"][-2:],
                   "presentation": selected["presentation_vi"] + ("\n" + selected["additional_vi"] if selected.get("additional_vi") else ""),
                   "question": selected["question_vi"], "images": [{k: a[k] for k in ("asset_id", "alt", "width", "height")} for a in assets],
                   "notice": "Bài biên soạn từ ca công bố, chưa được chuyên gia duyệt; không đại diện cho mọi ca tương tự."}
        original = {**payload, "presentation": presentation_en + ("\n" + selected["additional_en"] if selected.get("additional_en") else ""), "question": selected["question_en"]}
        rows.append({"exercise_id": exercise_id, "kind": "authored_case", "demo": selected["demo"],
                     "learner": payload, "learner_en": original, "criteria": criteria, "evidence": evidence,
                     "source": source, "assets": assets, "answer_annotations": [],
                     "selection_reason": selected["reason"], "source_case_id": case["case_id"],
                     "source_variant_note": case["source_variant_note"],
                     "translation_ref": {"source_id": source_id, "locator": block["locator"], "block_id": block["block_id"],
                                         "source_presentation_en": presentation_en, "translation_method": "manual_selected_translation_not_new_clinical_facts"}})
    for selected in spec["imaging_selections"]:
        study = next(s for s in studies if s["original_study_id"]["patient_id"] == selected["patient_id"])
        exercise_id = PREFIX + selected["key"]
        target = images[selected["target_image"]]
        ordered = [target] + [images[i] for i in study["image_ids"] if i != target["image_id"]]
        boxes = [a["bbox_original"] for a in target["annotations"] if a["name"] == "fracture"]
        if len(boxes) != 1 or target["source_row"]["diagnosis_uncertain"]:
            raise ValueError("imaging_target_not_unambiguous")
        box = boxes[0]
        col = min(2, int((box["xmin"]+box["xmax"])/2 / target["width"]*3))
        row = min(2, int((box["ymin"]+box["ymax"])/2 / target["height"]*3))
        cell = ["trên", "giữa", "dưới"][row] + "–" + ["trái", "giữa", "phải"][col]
        assets = [learner_asset(exercise_id, image, i+1) for i, image in enumerate(ordered)]
        sid = exercise_id + "_SU01"
        content = (f"The source Pascal VOC annotation labels one object 'fracture' on the first displayed image. "
                   f"Original pixel box: xmin={box['xmin']}, ymin={box['ymin']}, xmax={box['xmax']}, ymax={box['ymax']}; "
                   f"image width={target['width']}, height={target['height']}. A project-computed 3x3 grid places the box center in row {row+1}, column {col+1}. "
                   "This grid location is derived from the original annotation, not a radiologist's additional diagnosis. No treatment label is provided.")
        ref = {"source_id": target["source_id"], "annotation_path": target["annotation_refs"][0],
               "annotation_sha256": sha((DATA / target["annotation_refs"][0]).read_bytes()),
               "original_image_id": target["image_id"], "original_row": target["source_row"],
               "locator": "Pascal VOC /annotation/object[name='fracture']/bndbox", "bbox_original": box,
               "derived_grid": {"row": row+1, "column": col+1}, "source_image_sha256": target["sha256"]}
        criteria = [
            {"criterion_id": exercise_id + "_C01", "description": "Nhận diện vùng gãy xương trên ảnh số 1", "max_score": 1.0,
             "reference_answer_en": "Fracture", "reference_answer_vi": "Gãy xương", "acceptable_variants": ["fracture", "tổn thương gãy xương"],
             "common_incorrect_claims": [], "required_source_unit_ids": [sid], "kg_links": []},
            {"criterion_id": exercise_id + "_C02", "description": "Vị trí tâm vùng tổn thương theo lưới 3×3 trên ảnh số 1", "max_score": 1.0,
             "reference_answer_en": f"Grid row {row+1}, column {col+1}", "reference_answer_vi": "Ô " + cell,
             "acceptable_variants": [f"hàng {row+1}, cột {col+1}", f"row {row+1}, column {col+1}"],
             "common_incorrect_claims": [], "required_source_unit_ids": [sid], "kg_links": []},
        ]
        payload = {"exercise_id": exercise_id, "title": "Đọc X-quang " + selected["key"][-2:],
                   "presentation": "Lượt chụp X-quang cổ tay trẻ em từ dataset công bố. Giữ các góc chụp cùng lượt; chỉ hỏi ảnh số 1, các ảnh còn lại để đối chiếu. Không có bệnh sử hoặc xử trí đi kèm trong mẫu này.",
                   "question": "1. Nêu tổn thương chính trên ảnh số 1. 2. Chia ảnh thành lưới 3×3: cho biết ô chứa tâm vùng tổn thương (hàng trên/giữa/dưới và cột trái/giữa/phải, tính theo ảnh hiển thị). Trả lời bằng chữ, không cần click. Không yêu cầu phân loại gãy hoặc điều trị.",
                   "images": [{k: a[k] for k in ("asset_id", "alt", "width", "height")} for a in assets],
                   "notice": "Bài biên soạn từ annotation dataset; nhãn có thể chưa đầy đủ. Không suy ảnh không có box là bình thường."}
        original = {**payload, "presentation": "Published pediatric wrist radiographs. All selected study views remain grouped; only image 1 is assessed. No clinical history or management data are supplied.",
                    "question": "1. Identify the principal finding in image 1. 2. State the 3x3 grid cell containing its center (top/middle/bottom row and left/middle/right column as displayed). Answer in text; no clicking, fracture classification or treatment is requested."}
        rows.append({"exercise_id": exercise_id, "kind": "authored_imaging", "demo": selected["demo"], "learner": payload, "learner_en": original,
                     "criteria": criteria, "evidence": [{"source_unit_id": sid, "content_en": content, "source_ref": ref, "description_origin": "deterministic_description_of_dataset_annotation", "source_id": target["source_id"]}],
                     "assets": assets, "source": sources[target["source_id"]],
                     "answer_annotations": [{"asset_id": assets[0]["asset_id"], "box": box, "label": "fracture"}],
                     "source_study_id": study["study_id"], "patient_group_id": study["patient_group_id"],
                     "selection_reason": "Ảnh mục tiêu có một box fracture, không gắn cờ diagnosis_uncertain; giữ cả lượt chụp, chưa suy diễn chẩn đoán hoặc xử trí.",
                     "translation_ref": {"translation_method": "manual_translation_of_authored_task_not_a_source_case_history"}})
    manifest = []
    for row in rows:
        row.update(expert_verified=False, source_check_status="checked_against_local_sources_not_expert_reviewed", max_score=2.0,
                   course_id=None, topic_id=None, kg_mapping_status="manual_exact_meaning_links_where_available_otherwise_pending")
        row["packet"] = packet(row["exercise_id"], row["source"], row["evidence"])
        write(OUT / "learner" / (row["exercise_id"] + ".vi.json"), row["learner"])
        write(OUT / "learner" / (row["exercise_id"] + ".en.json"), row["learner_en"])
        grading = {k: v for k, v in row.items() if k not in ("learner", "learner_en")}
        write(OUT / "grading" / (row["exercise_id"] + ".json"), grading)
        write(OUT / "translations" / (row["exercise_id"] + ".json"), {"en": row["learner_en"], "vi": row["learner"], "provenance": row["translation_ref"]})
        manifest.append({"exercise_id": row["exercise_id"], "demo": row["demo"], "kind": row["kind"], "learner_path": "learner/" + row["exercise_id"] + ".vi.json", "grading_path": "grading/" + row["exercise_id"] + ".json"})
    write(OUT / "manifest.json", {"format": "clinical-authored-exercises-v1", "expert_verified": False, "rows": manifest,
                                  "demo_ids": [r["exercise_id"] for r in rows if r["demo"]]})
    return rows


if __name__ == "__main__":
    print(json.dumps({"exercises": len(build())}, ensure_ascii=False))
