"""Mechanical provenance checks, explicitly distinct from medical review."""

import re
import unicodedata

from jsonschema import Draft202012Validator


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def markers(text):
    # Conservative exact tokens: no fuzzy OCR repair for doses, signs or negation.
    pattern = r"\d+(?:[.,]\d+)?|[<>≤≥=]|\b(?:không|chưa|nếu|trừ|phải|chỉ|khi|mg|ml|cm|mm|giờ)\b"
    return re.findall(pattern, normalized(text).lower())


def validate_extraction(value, chunk, schema):
    Draft202012Validator(schema).validate(value)
    spans = {x["span_id"]: x for x in chunk["source_spans"]}
    units = {}
    concepts = {}
    statements = {}
    for collection, index in (
        ("source_units", units),
        ("concepts", concepts),
        ("statements", statements),
    ):
        for row in value[collection]:
            key = row["local_id"]
            if key in index:
                raise ValueError("Duplicate local ID")
            index[key] = row
    for unit in units.values():
        for support in unit["supports"]:
            span = spans.get(support["span_id"])
            if span is None:
                raise ValueError("Dangling source span")
            quote = support["quote"]
            if normalized(quote) not in normalized(span["text"]):
                raise ValueError("Quote not found in specified source span")
            # Normalization only allows NFC/whitespace. Numeric/OCR changes are rejected.
            if not quote.strip():
                raise ValueError("Empty quote")
    for concept in concepts.values():
        if not set(concept["source_unit_ids"]) <= units.keys():
            raise ValueError("Dangling concept source unit")
        supports = [
            s["quote"]
            for key in concept["source_unit_ids"]
            for s in units[key]["supports"]
        ]
        for name in [concept["verbatim_name"], *concept["aliases"]]:
            if not any(normalized(name) in normalized(q) for q in supports):
                raise ValueError("Unsupported concept name or alias")
    for statement in statements.values():
        if not set(statement["concept_ids"]) <= concepts.keys():
            raise ValueError("Dangling statement concept")
        if not set(statement["source_unit_ids"]) <= units.keys():
            raise ValueError("Dangling statement source unit")
        quotes = [
            s["quote"]
            for key in statement["source_unit_ids"]
            for s in units[key]["supports"]
        ]
        if any(
            not any(normalized(q) in normalized(source) for source in quotes)
            for q in statement["quotes"]
        ):
            raise ValueError("Statement quote not supported by linked source units")
        # Text is deliberately extractive in this MVP; interpretation stays in a separate field.
        # Thus numbers, units, qualifiers and negatives cannot silently vanish from a quote.
        if normalized(statement["text"]) != normalized("\n".join(statement["quotes"])):
            raise ValueError(
                "Statement text must retain complete supporting quotations"
            )
        if markers(statement["text"]) != markers("\n".join(statement["quotes"])):
            raise ValueError("Numeric/conditional markers changed")
        joined = "\n".join(statement["quotes"])
        for key in ("conditions", "negations", "requirements", "temporal_information"):
            if any(normalized(t) not in normalized(joined) for t in statement[key]):
                raise ValueError("Unsupported qualifier")
        if statement["sequence"] and not statement["procedure_context"]:
            raise ValueError("Sequence requires version-specific procedure context")
        relation = statement["relation"]
        if relation and not {
            relation["subject_concept_id"],
            relation["object_concept_id"],
        } <= set(statement["concept_ids"]):
            raise ValueError("Dangling relation concept")
        if (
            statement["extraction_kind"] == "direct"
            and statement["interpretation"] is not None
        ):
            raise ValueError("Interpretation must not be labelled direct extraction")
        for step in statement["sequence"]:
            if normalized(step["quote"]) not in normalized(joined):
                raise ValueError("Unsupported procedure step")
        orders = [s["position"] for s in statement["sequence"]]
        if len(set(orders)) != len(orders):
            raise ValueError("Duplicate procedure position")
    return {
        "json_schema": "passed",
        "quote_locator": "passed",
        "semantic_support": "needs_review",
        "expert_review": "unverified",
    }
