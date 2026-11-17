"""Local collection contracts, intentionally separate from Question/Rubric/import schemas."""
from jsonschema import Draft202012Validator

TEXT = {"type": "string", "minLength": 1}
NULL_TEXT = {"type": ["string", "null"]}
TEXTS = {"type": "array", "items": TEXT}


def schema(properties):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
            "properties": properties, "required": list(properties), "additionalProperties": True}


SCHEMAS = {
    "ClinicalCase": schema({
        "case_id": TEXT, "title": TEXT, "specialty": {"enum": ["orthopedics", "surgical_emergency"]},
        "data_kind": {"const": "published_clinical_case"}, "topics": TEXTS,
        **{k: NULL_TEXT for k in ("presentation", "investigations", "reference_diagnosis", "management", "outcome")},
        "image_ids": TEXTS, "source_refs": {"type": "object"}, "expert_verified": {"const": False},
        "extraction_method": {"const": "manual_excerpt_selection_no_LLM_no_OCR"},
    }),
    "MedicalImage": schema({
        "image_id": TEXT, "case_id": NULL_TEXT, "study_id": NULL_TEXT,
        "modality": {"enum": ["XR", "CT", "MRI", "mixed_radiology", "endoscopy", "specimen_photo", "operative_photo", "illustration"]},
        "body_region": TEXT, "view": NULL_TEXT, "local_path": TEXT, "original_url": TEXT,
        "caption": NULL_TEXT, "annotation_refs": TEXTS, "source_id": TEXT,
        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "width": {"type": "integer", "minimum": 1}, "height": {"type": "integer", "minimum": 1},
        "expert_verified": {"const": False},
    }),
    "Source": schema({
        "source_id": TEXT, "title": TEXT, "authors": TEXTS, "year": {"type": ["integer", "null"]},
        "doi": TEXT, "dataset_version": {"type": ["integer", "null"]},
        "original_url": TEXT, "license": TEXT, "license_url": TEXT,
        "attribution_text": TEXT, "retrieval_date": TEXT,
    }),
    "ImagingStudy": schema({
        "study_id": TEXT, "dataset_source_id": TEXT, "original_study_id": {"type": "object"},
        "patient_group_id": TEXT, "image_ids": TEXTS, "labels": {"type": "array"},
        "annotation_refs": TEXTS, "split": {"const": "unassigned_review_only"}, "expert_verified": {"const": False},
    }),
}

SCHEMAS["MedicalImage"]["oneOf"] = [
    {"properties": {"case_id": TEXT, "study_id": {"type": "null"}}},
    {"properties": {"case_id": {"type": "null"}, "study_id": TEXT}},
]


def validate_records(name, records):
    validator = Draft202012Validator(SCHEMAS[name])
    for record in records:
        validator.validate(record)
