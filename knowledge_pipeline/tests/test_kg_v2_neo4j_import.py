import copy
import json

import pytest

from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import build_plan, verify_result


def source(excerpt="Book statement", locator="l1"):
    return {
        "source_id": "book",
        "locator_id": locator,
        "pdf_pages": [1],
        "printed_pages": ["1"],
        "excerpt": excerpt,
    }


def graph():
    def node(identifier, name):
        return {
            "id": identifier,
            "type": "Condition",
            "name": name,
            "aliases": [],
            "content": [{"text": "Book statement", "sources": [source()]}],
        }

    return {
        "schema_version": "medical-kg-v2",
        "nodes": [node("a", "Subtype"), node("b", "Parent")],
        "edges": [
            {
                "id": "e",
                "from_id": "a",
                "to_id": "b",
                "type": "IS_A",
                "condition": None,
                "sources": [source()],
            }
        ],
    }


def snapshot(g):
    payload = dry_run_loader(g)
    return {
        "nodes": [
            {
                "element_id": r["properties"]["id"],
                "labels": r["labels"],
                "properties": r["properties"],
            }
            for r in payload["nodes"]
        ],
        "relationships": [
            {
                "element_id": r["properties"]["id"],
                "start_node": r["from_id"],
                "end_node": r["to_id"],
                "type": r["type"],
                "properties": r["properties"],
            }
            for r in payload["edges"]
        ],
    }


def test_additive_content_sources_unmanaged_properties_and_idempotency():
    old = snapshot(graph())
    old["nodes"][0]["properties"]["custom"] = "keep me"
    old["relationships"][0]["properties"]["custom"] = "edge extra"
    incoming = graph()
    incoming["nodes"][0]["content"][0]["sources"].append(source(locator="second"))
    incoming["nodes"][0]["content"].append(
        {
            "text": "Different condition",
            "sources": [source("Different condition", "l3")],
        }
    )
    incoming["edges"][0]["sources"].append(source(locator="second"))
    old_bytes = json.dumps(old, sort_keys=True)
    plan = build_plan(incoming, old)
    assert plan["counts"] == {"nodes": {"update": 1, "skip": 1}, "edges": {"update": 1}}
    assert json.dumps(old, sort_keys=True) == old_bytes
    merged = copy.deepcopy(old)
    for target, row in zip(merged["nodes"], plan["nodes"]):
        target["properties"].update(row["properties"])
    merged["relationships"][0]["properties"].update(plan["edges"][0]["properties"])
    assert merged["nodes"][0]["properties"]["custom"] == "keep me"
    assert merged["relationships"][0]["properties"]["custom"] == "edge extra"
    contents = json.loads(merged["nodes"][0]["properties"]["content"])
    assert len(contents) == 2 and len(contents[0]["sources"]) == 2
    assert verify_result(old, merged, plan)["decoded_sources_match"]
    assert build_plan(incoming, merged)["counts"] == {
        "nodes": {"skip": 2},
        "edges": {"skip": 1},
    }


@pytest.mark.parametrize(
    "conflict", ["duplicate_id", "label", "name", "edge_type", "condition"]
)
def test_existing_contract_conflicts_stop_before_writes(conflict):
    old = snapshot(graph())
    if conflict == "duplicate_id":
        old["nodes"].append(copy.deepcopy(old["nodes"][0]))
    if conflict == "label":
        old["nodes"][0]["labels"] = ["MedicalConcept", "Intervention"]
    if conflict == "name":
        old["nodes"][0]["properties"]["name"] = "Another object"
    if conflict == "edge_type":
        old["relationships"][0]["type"] = "MAY_CAUSE"
    if conflict == "condition":
        old["relationships"][0]["properties"]["condition"] = "Only if"
    with pytest.raises(ValueError):
        build_plan(graph(), old)


def test_unrelated_changes_and_content_loss_are_detected():
    old = snapshot(graph())
    old["nodes"].append(
        {
            "element_id": "outside",
            "labels": ["Unrelated"],
            "properties": {"id": "outside", "note": "original"},
        }
    )
    plan = build_plan(graph(), old)
    after = copy.deepcopy(old)
    after["nodes"][-1]["properties"]["note"] = "changed"
    with pytest.raises(ValueError, match="outside_scope"):
        verify_result(old, after, plan)
    after = copy.deepcopy(old)
    after["nodes"][0]["properties"]["content"] = "[]"
    with pytest.raises(ValueError, match="readback"):
        verify_result(old, after, plan)


def test_cycle_crossing_existing_hierarchy_is_rejected():
    old = snapshot(graph())
    old["relationships"][0].update(start_node="b", end_node="a", element_id="existing")
    old["relationships"][0]["properties"]["id"] = "existing"
    with pytest.raises(ValueError, match="cycle_with_existing"):
        build_plan(graph(), old)
