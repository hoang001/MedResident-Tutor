"""Pure Neo4j loader preview. Deliberately has no database driver / apply operation."""

import json

from jsonschema import Draft202012Validator

from .contracts import MEDICAL, RELATIONS, schemas
from .validation import cycle_if_added

NESTED = {"content", "sources", "answer_sources"}


def encode_properties(node):
    return {
        key: json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in NESTED
        else value
        for key, value in node.items()
        if key != "type" and value is not None
    }


def decode_properties(properties, node_type):
    node = {
        "type": node_type,
        **{
            key: json.loads(value) if key in NESTED else value
            for key, value in properties.items()
        },
    }
    if node_type == "SampleQuestion":
        node.setdefault("answer", None)
        node.setdefault("explanation", None)
    return node


def decode_relationship(row):
    props = row["properties"]
    return {
        "id": props["id"],
        "from_id": row["from_id"],
        "to_id": row["to_id"],
        "type": row["type"],
        "condition": props.get("condition"),
        "sources": json.loads(props["sources"]),
    }


def dry_run_loader(graph):
    Draft202012Validator(schemas()[1]).validate(graph)
    ids = {n["id"]: n for n in graph["nodes"]}
    if len(ids) != len(graph["nodes"]):
        raise ValueError("duplicate_target_node_id")
    edges, edge_ids = [], set()
    for edge in graph["edges"]:
        if edge["id"] in edge_ids:
            raise ValueError("duplicate_target_edge_id")
        edge_ids.add(edge["id"])
        if edge["from_id"] not in ids or edge["to_id"] not in ids:
            raise ValueError("dangling_target_edge")
        domain, range_ = RELATIONS[edge["type"]]
        left, right = ids[edge["from_id"]]["type"], ids[edge["to_id"]]["type"]
        if (
            left not in domain
            or right not in range_
            or edge["type"] == "IS_A"
            and left != right
        ):
            raise ValueError("invalid_target_edge_types")
        if cycle_if_added(edges, edge):
            raise ValueError("target_hierarchy_cycle")
        edges.append(edge)
    node_rows = []
    for node in graph["nodes"]:
        properties = encode_properties(node)
        if decode_properties(properties, node["type"]) != node:
            raise ValueError("neo4j_json_roundtrip_failed")
        node_rows.append(
            {
                "labels": ["MedicalConcept", node["type"]]
                if node["type"] in MEDICAL
                else [node["type"]],
                "properties": properties,
            }
        )
    edge_rows = []
    for edge in edges:
        props = {
            "id": edge["id"],
            "condition": edge["condition"],
            "sources": json.dumps(edge["sources"], ensure_ascii=False, sort_keys=True),
        }
        if json.loads(props["sources"]) != edge["sources"]:
            raise ValueError("edge_sources_roundtrip_failed")
        if props["condition"] is None:
            props.pop("condition")
        row = {
            "type": edge["type"],
            "from_id": edge["from_id"],
            "to_id": edge["to_id"],
            "properties": props,
        }
        if decode_relationship(row) != edge:
            raise ValueError("edge_nullable_property_roundtrip_failed")
        edge_rows.append(row)
    return {
        "mode": "dry_run_only",
        "neo4j_imported": False,
        "publication_authorized": False,
        "nodes": node_rows,
        "edges": edge_rows,
    }
