import copy

import pytest

from document_toolkit.common import read_json
from scripts.import_curriculum import (
    SOURCE,
    TREE_SOURCE,
    build_curriculum_tree,
    build_plan,
    build_skeleton,
    verify_graph,
)


def stored(graph):
    nodes = [
        {
            "element_id": n["properties"]["id"],
            "labels": ["CurriculumEntity", n["type"]],
            "properties": copy.deepcopy(n["properties"]),
        }
        for n in graph["nodes"]
    ]
    edges = [
        {
            "element_id": e["properties"]["id"],
            "type": e["type"],
            "start_node": e["from_id"],
            "end_node": e["to_id"],
            "properties": copy.deepcopy(e["properties"]),
        }
        for e in graph["edges"]
    ]
    return {"nodes": nodes, "relationships": edges}


def test_source_curriculum_keeps_elective_requirement_and_empty_course_content():
    graph = build_skeleton(read_json(SOURCE))
    courses = [n["properties"] for n in graph["nodes"] if n["type"] == "Course"]
    assert len(courses) == 13
    assert all(
        not {"content_outline", "learning_outcomes", "prerequisites"} & n.keys()
        for n in courses
    )
    advanced = next(
        n["properties"]
        for n in graph["nodes"]
        if n["properties"].get("round") == 3 and n["type"] == "CurriculumGroup"
    )
    assert advanced["total_credits_required"] == 16
    assert sum(c["total_credits"] for c in courses if c["round"] == 3) == 32
    assert (
        next(c for c in courses if c["course_code"] == "B21CN1")["curriculum_group_id"]
        == "ORTHO_FOUNDATION_ROUND_1"
    )


def test_collision_with_medical_node_refuses_import():
    graph = build_skeleton(read_json(SOURCE))
    before = stored(graph)
    before["nodes"][0]["labels"] = ["Condition", "MedicalConcept"]
    with pytest.raises(ValueError, match="collision_with_other_data"):
        build_plan(graph, before)


def test_rerun_preserves_later_teacher_content_and_needs_no_writes():
    graph = build_skeleton(read_json(SOURCE))
    before = stored(graph)
    course = next(n for n in before["nodes"] if "Course" in n["labels"])
    course["properties"].update(
        content_status="provided", content_outline="Teacher-provided outline"
    )
    plan = build_plan(graph, before)
    assert plan["nodes_to_create"] == plan["edges_to_create"] == 0
    result = verify_graph(graph, before, copy.deepcopy(before), plan)
    assert result["writes_needed_on_rerun"] == 0


def test_readback_rejects_any_change_to_preexisting_book_data():
    graph = build_skeleton(read_json(SOURCE))
    before = stored(graph)
    before["nodes"].append(
        {
            "element_id": "medical",
            "labels": ["Condition", "MedicalConcept"],
            "properties": {"id": "old-book-node", "name": "Existing book content"},
        }
    )
    plan = build_plan(graph, before)
    after = copy.deepcopy(before)
    after["nodes"][-1]["properties"]["name"] = "Accidental overwrite"
    with pytest.raises(ValueError, match="preexisting_graph_data_changed"):
        verify_graph(graph, before, after, plan)


def test_full_list_preserves_known_codes_and_does_not_invent_missing_metadata():
    legacy = build_skeleton(read_json(SOURCE))
    graph = build_curriculum_tree(read_json(TREE_SOURCE), legacy)
    courses = [n for n in graph["nodes"] if n["type"] == "Course"]
    assert len(courses) == 27
    assert len(graph["nodes"]) == 38
    assert len(graph["edges"]) == 37
    known = {n["properties"]["id"] for n in legacy["nodes"] if n["type"] == "Course"}
    assert known <= {n["properties"]["id"] for n in courses}
    new = [n["properties"] for n in courses if n["properties"]["id"] not in known]
    assert len(new) == 14
    assert all(
        not {"total_credits", "theory_credits", "practice_credits"} & n.keys()
        for n in new
    )
    for course in new:
        if course.get("course_code"):
            assert course["course_code_status"] == "verified_hmu_public_listing"
            assert course["year_status"] == "verified_hmu_lms_year_listing"
        else:
            assert "year" not in course
    requirements = [n for n in graph["nodes"] if n["type"] == "CurriculumRequirement"]
    assert len(requirements) == 1
    assert requirements[0]["properties"]["required_level"] == "Bậc 4/6"
    groups = {
        n["properties"].get("group_id"): n["properties"]
        for n in graph["nodes"]
        if n["type"] == "CurriculumGroup"
    }
    assert (
        groups["GENERAL_ELECTIVE"]["selection_choose"],
        groups["GENERAL_ELECTIVE"]["selection_from"],
    ) == (1, 3)
    assert (
        groups["ORTHO_ADVANCED_CLINICAL_ROUND_3"]["selection_choose"],
        groups["ORTHO_ADVANCED_CLINICAL_ROUND_3"]["selection_from"],
    ) == (4, 8)


def test_migration_reparents_only_old_group_links_and_preserves_teacher_content():
    legacy = build_skeleton(read_json(SOURCE))
    graph = build_curriculum_tree(read_json(TREE_SOURCE), legacy)
    before = stored(legacy)
    teacher_course = next(n for n in before["nodes"] if "Course" in n["labels"])
    teacher_course["properties"].update(
        content_outline="Teacher's outline", content_status="provided"
    )
    before["nodes"].append(
        {
            "element_id": "medical",
            "labels": ["Condition", "MedicalConcept"],
            "properties": {"id": "book-node", "name": "Book content"},
        }
    )
    plan = build_plan(graph, before, legacy)
    assert (
        plan["nodes_to_create"],
        plan["edges_to_create"],
        plan["nodes_to_update"],
        plan["edges_to_delete"],
    ) == (21, 24, 3, 3)
    assert all(
        e["type"] == "HAS_GROUP"
        and e["start_node"] == legacy["nodes"][0]["properties"]["id"]
        for e in plan["delete_edges"]
    )
    after = stored(graph)
    for row in before["nodes"]:
        target = next(
            (n for n in after["nodes"] if n["element_id"] == row["element_id"]), None
        )
        if target:
            target["properties"] = {**row["properties"], **target["properties"]}
        else:
            after["nodes"].append(copy.deepcopy(row))
    verification = verify_graph(graph, before, after, plan, legacy)
    assert verification["non_curriculum_nodes_unchanged"] == 1
    rerun = build_plan(graph, after, legacy)
    assert all(
        rerun[k] == 0
        for k in [
            "nodes_to_create",
            "nodes_to_update",
            "edges_to_create",
            "edges_to_delete",
        ]
    )
    course = next(
        n for n in after["nodes"] if n["element_id"] == teacher_course["element_id"]
    )
    assert course["properties"]["content_outline"] == "Teacher's outline"
    assert course["properties"]["content_status"] == "provided"


def test_migration_refuses_concurrent_edit_to_managed_metadata():
    legacy = build_skeleton(read_json(SOURCE))
    graph = build_curriculum_tree(read_json(TREE_SOURCE), legacy)
    before = stored(legacy)
    before["nodes"][0]["properties"]["source_scope"] = "User-edited source scope"
    with pytest.raises(ValueError, match="existing_curriculum_metadata_differs"):
        build_plan(graph, before, legacy)


def test_full_tree_refuses_group_cycles():
    tree = read_json(TREE_SOURCE)
    tree["course_groups"][0]["parent_group_id"] = "GENERAL_ELECTIVE"
    with pytest.raises(ValueError, match="invalid_curriculum_parent_or_cycle"):
        build_curriculum_tree(tree, build_skeleton(read_json(SOURCE)))


def test_sourced_official_code_does_not_change_an_internal_course_identity():
    tree = read_json(TREE_SOURCE)
    legacy = build_skeleton(read_json(SOURCE))
    course = next(
        c for g in tree["course_groups"] for c in g["courses"] if c.get("internal_key")
    )
    for key in ["course_code", "course_code_status", "year", "year_status"]:
        course.pop(key, None)
    before = build_curriculum_tree(tree, legacy)
    course.update(
        course_code="SĐH001",
        course_code_status="verified_hmu_public_listing",
        year=1,
        year_status="verified_hmu_lms_year_listing",
    )
    after = build_curriculum_tree(tree, legacy)
    assert {n["properties"]["id"] for n in before["nodes"]} == {
        n["properties"]["id"] for n in after["nodes"]
    }
