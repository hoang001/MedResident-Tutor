import copy

import pytest

from knowledge_pipeline.kg_v2.loader import dry_run_loader
from scripts.complete_2021_book import (
    entity_type_issue,
    literal_present,
    phrase_present,
    retained_ranges,
)
from scripts.import_2021_completion import repair_plan, verify_snapshot


def graph():
    source = {
        "source_id": "book",
        "locator_id": "loc",
        "pdf_pages": [8],
        "printed_pages": [],
        "excerpt": "Verified source statement.",
    }
    return {
        "schema_version": "medical-kg-v2",
        "nodes": [
            {
                "id": key,
                "type": "Condition",
                "name": name,
                "aliases": [],
                "content": [{"text": source["excerpt"], "sources": [source]}],
            }
            for key, name in [("a", "Subtype"), ("b", "Parent")]
        ],
        "edges": [
            {
                "id": "old-edge",
                "from_id": "a",
                "to_id": "b",
                "type": "IS_A",
                "condition": None,
                "sources": [source],
            }
        ],
    }


def snapshot(value):
    rows = dry_run_loader(value)
    return {
        "nodes": [{"element_id": n["properties"]["id"], **n} for n in rows["nodes"]],
        "relationships": [
            {
                "element_id": e["properties"]["id"],
                "type": e["type"],
                "start_node": e["from_id"],
                "end_node": e["to_id"],
                "properties": e["properties"],
            }
            for e in rows["edges"]
        ],
    }


def incoming():
    value = graph()
    value["nodes"][0]["name"] = "Corrected source name"
    value["edges"][0]["id"] = "new-edge"
    return value


def test_scoped_repair_updates_verified_content_preserves_unmanaged_fields():
    old = graph()
    before = snapshot(old)
    before["nodes"][0]["properties"]["custom_note"] = "Keep this"
    frozen = copy.deepcopy(before)
    plan = repair_plan(incoming(), before, before, old)
    assert before == frozen
    assert plan["nodes"][0]["properties"]["custom_note"] == "Keep this"
    assert plan["nodes"][0]["properties"]["name"] == "Corrected source name"
    assert [e["properties"]["id"] for e in plan["delete_edges"]] == ["old-edge"]
    assert plan["delete_nodes"] == []


def test_foreign_identity_collision_is_refused():
    old = graph()
    before = snapshot(old)
    extra = copy.deepcopy(before["nodes"][0])
    extra["element_id"] = "foreign-element"
    extra["properties"]["id"] = "foreign"
    before["nodes"].append(extra)
    new = incoming()
    new_node = copy.deepcopy(new["nodes"][0])
    new_node["id"] = "foreign"
    new["nodes"].append(new_node)
    with pytest.raises(ValueError, match="foreign_node_identity_collision"):
        repair_plan(new, before, before, old)


def test_foreign_relationship_incident_to_book_is_refused():
    before = snapshot(graph())
    extra = copy.deepcopy(before["relationships"][0])
    extra["element_id"] = "external-edge"
    extra["properties"]["id"] = "external-edge"
    before["relationships"].append(extra)
    with pytest.raises(ValueError, match="foreign_relationship_touches_owned_book"):
        repair_plan(incoming(), before, before, graph())


def test_concurrent_change_to_previously_imported_book_is_refused():
    baseline = snapshot(graph())
    current = copy.deepcopy(baseline)
    current["nodes"][0]["properties"]["name"] = "User edit"
    with pytest.raises(ValueError, match="changed_since_snapshot"):
        repair_plan(incoming(), current, baseline, graph())


def test_readback_verification_refuses_changes_outside_book():
    before = snapshot(graph())
    foreign = copy.deepcopy(before["nodes"][0])
    foreign["element_id"] = "outside"
    foreign["properties"]["id"] = "outside"
    before["nodes"].append(foreign)
    plan = repair_plan(incoming(), before, before, graph())
    after = snapshot(incoming())
    for node in after["nodes"]:
        node["properties"] = copy.deepcopy(
            next(
                r["properties"]
                for r in plan["nodes"]
                if r["properties"]["id"] == node["properties"]["id"]
            )
        )
    after["relationships"][0]["properties"] = copy.deepcopy(
        plan["edges"][0]["properties"]
    )
    after["nodes"].append(copy.deepcopy(foreign))
    after["nodes"][-1]["properties"]["name"] = "Unintended change"
    with pytest.raises(ValueError, match="outside_book_data_changed"):
        verify_snapshot(before, after, plan)


def test_identity_requires_whole_tokens_including_roman_degree():
    assert phrase_present("Độ I", "Phân loại: Độ I; Độ II.")
    assert not phrase_present("Độ I", "Độ III: Vết thương nặng.")
    assert not phrase_present("chữa", "chưa điều trị")
    assert phrase_present(
        "Gãy trên lồi cầu xương cánh tay",
        "Gãy trên lồi cầu (TLC) xương cánh tay ở trẻ em",
    )
    assert not phrase_present("dấu hiệu tăng áp lực", "dấu hiệu (không có) tăng áp lực")
    assert phrase_present("IFSSH", "Hiệp hội quốc tế (IFSSH)")


def test_independent_numeric_matching_preserves_values_and_signs():
    assert literal_present("30⁰", "Góc 30°")
    assert not literal_present(">30 mmHg", "<30 mmHg")
    assert not literal_present("150", "1500")
    assert not literal_present("không điều trị", "điều trị")


def test_real_draft_typing_errors_do_not_become_medical_facts():
    assert entity_type_issue("Intervention", "Kim Kirschner")
    assert entity_type_issue("Intervention", "Khung cố định ngoài")
    assert entity_type_issue("Intervention", "Đóng đinh nội tủy") is None
    assert entity_type_issue("Intervention", "Vít qua khớp C1-C2") is None
    assert entity_type_issue("Intervention", "Nẹp cổ") is None
    assert entity_type_issue("Drug", "tụ cầu vàng (Staph. aureus)")
    assert entity_type_issue("Drug", "Chì thép")
    assert entity_type_issue("Finding", "Phi toxin")
    assert entity_type_issue("Condition", "Tai nạn giao thông")
    assert entity_type_issue("ClinicalPrinciple", "Cơ chế chấn thương trực tiếp")
    assert entity_type_issue("Condition", "Nhiễm trùng do tụ cầu vàng") is None
    assert entity_type_issue("Drug", "Clindamycin") is None
    assert entity_type_issue("ClinicalPrinciple", "Cố định sinh học") is None


def test_repeated_pdf_paragraph_keeps_each_exact_locator_verifiable():
    from scripts.finalize_2021_book import content_per_locator

    first = {
        "excerpt": "Exact repeated paragraph.",
        "locator_id": "page-155",
        "pdf_pages": [155],
    }
    second = {"excerpt": first["excerpt"], "locator_id": "page-157", "pdf_pages": [157]}
    result = content_per_locator(
        [
            {"text": first["excerpt"], "sources": [first, second]},
            {"text": first["excerpt"], "sources": [first]},
        ]
    )
    assert len(result) == 2
    assert {b["sources"][0]["locator_id"] for b in result} == {"page-155", "page-157"}
    assert all(
        b["text"] == "\n".join(s["excerpt"] for s in b["sources"]) for b in result
    )


def test_layout_filter_splits_ranges_without_dropping_retained_conditions():
    assert retained_ranges([[8, 1, 7]], {8: {1, 2, 4, 5, 7}}) == [
        [8, 1, 2],
        [8, 4, 5],
        [8, 7, 7],
    ]
