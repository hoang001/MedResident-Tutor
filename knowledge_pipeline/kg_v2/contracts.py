"""Controlled vocabulary and separate extraction / graph JSON contracts."""

MEDICAL = [
    "Condition",
    "Anatomy",
    "Finding",
    "Classification",
    "ClassificationCategory",
    "DiagnosticMethod",
    "Intervention",
    "Drug",
    "ClinicalPrinciple",
]
TYPES = MEDICAL + ["Skill", "SampleQuestion"]
RELATIONS = {
    "IS_A": (set(MEDICAL), set(MEDICAL)),
    "LOCATED_IN": ({"Condition"}, {"Anatomy"}),
    "HAS_FINDING": ({"Condition"}, {"Finding"}),
    "CLASSIFIED_BY": ({"Condition"}, {"Classification"}),
    "HAS_CATEGORY": ({"Classification"}, {"ClassificationCategory"}),
    "EVALUATED_BY": ({"Condition"}, {"DiagnosticMethod"}),
    "MANAGED_BY": ({"Condition"}, {"Intervention"}),
    "USES_DRUG": ({"Intervention"}, {"Drug"}),
    "MAY_CAUSE": ({"Condition", "Intervention"}, {"Condition"}),
    "GUIDED_BY": ({"Condition", "Intervention"}, {"ClinicalPrinciple"}),
    "APPLIES_TO": ({"Skill"}, set(MEDICAL)),
    "REQUIRES_KNOWLEDGE_OF": ({"Skill"}, set(MEDICAL)),
    "HAS_SUBSKILL": ({"Skill"}, {"Skill"}),
    "ABOUT": ({"SampleQuestion"}, set(MEDICAL)),
    "ASSESSES": ({"SampleQuestion"}, {"Skill"}),
}


def obj(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "required": list(properties) if required is None else required,
    }


TEXT = {"type": "string", "minLength": 1}
NULL_TEXT = {"type": ["string", "null"]}
STRINGS = {"type": "array", "items": TEXT}


def array(item, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum}


def schemas():
    support = obj({"block_id": TEXT, "excerpt": TEXT}, required=["block_id"])
    supports = array(support, 1)
    # Do not ask the model to repeat a quote twice: the program derives target content.text.
    content = array(obj({"sources": supports}), 1)
    medical = obj(
        {
            "local_id": TEXT,
            "type": {"enum": MEDICAL},
            "name": TEXT,
            "aliases": STRINGS,
            "identity_sources": supports,
            "content": content,
        }
    )
    skill = obj(
        {
            "local_id": TEXT,
            "type": {"const": "Skill"},
            "name": TEXT,
            "kind": {"enum": ["cognitive", "practical"]},
            "basis": {
                "enum": [
                    "learning_objective",
                    "practice_requirement",
                    "procedural_instruction",
                ]
            },
            "basis_sources": supports,
            "identity_sources": supports,
            "content": content,
        }
    )
    question = obj(
        {
            "local_id": TEXT,
            "type": {"const": "SampleQuestion"},
            "text": TEXT,
            "format": {
                "enum": ["open_ended", "multiple_choice", "case", "multipart", "other"]
            },
            "options": STRINGS,
            "answer": NULL_TEXT,
            "explanation": NULL_TEXT,
            "sources": supports,
            "answer_sources": array(support),
        }
    )
    edge = obj(
        {
            "local_id": TEXT,
            "from_id": TEXT,
            "to_id": TEXT,
            "type": {"enum": list(RELATIONS)},
            "condition": NULL_TEXT,
            "sources": supports,
        }
    )
    raw = obj(
        {"nodes": array({"oneOf": [medical, skill, question]}), "edges": array(edge)}
    )
    source = obj(
        {
            "source_id": TEXT,
            "locator_id": TEXT,
            "pdf_pages": array({"type": "integer", "minimum": 1}, 1),
            "printed_pages": STRINGS,
            "excerpt": TEXT,
        }
    )
    target_content = array(obj({"text": TEXT, "sources": array(source, 1)}), 1)
    targets = [
        obj(
            {
                "id": TEXT,
                "type": {"enum": MEDICAL},
                "name": TEXT,
                "aliases": STRINGS,
                "content": target_content,
            }
        ),
        obj(
            {
                "id": TEXT,
                "type": {"const": "Skill"},
                "name": TEXT,
                "kind": {"enum": ["cognitive", "practical"]},
                "content": target_content,
            }
        ),
        obj(
            {
                "id": TEXT,
                "type": {"const": "SampleQuestion"},
                "text": TEXT,
                "format": question["properties"]["format"],
                "options": STRINGS,
                "answer": NULL_TEXT,
                "explanation": NULL_TEXT,
                "sources": array(source, 1),
                "answer_sources": array(source),
            }
        ),
    ]
    graph = obj(
        {
            "schema_version": {"const": "medical-kg-v2"},
            "nodes": array({"oneOf": targets}),
            "edges": array(
                obj(
                    {
                        "id": TEXT,
                        "from_id": TEXT,
                        "to_id": TEXT,
                        "type": {"enum": list(RELATIONS)},
                        "condition": NULL_TEXT,
                        "sources": array(source, 1),
                    }
                )
            ),
        }
    )
    for schema in (raw, graph):
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return raw, graph
