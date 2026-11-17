"""Offline checks for the additive reading-map importer; no model/database needed."""

import copy
import unittest

from scripts.map_round2_books import (
    CATALOG,
    MANAGER,
    PROGRAM,
    SPEC,
    build_graph,
    citations,
    plan_changes,
    read_json,
    verify_preserved,
)


def fixture():
    spec, catalog = read_json(SPEC), read_json(CATALOG)
    nodes = []
    for i, code in enumerate(["B21CN7", "B21CN8", "B21CN9", "B21CN10"]):
        nodes.append({"element_id": "course-" + str(i), "labels": ["Course", "CurriculumEntity"],
                      "properties": {"id": "CURRICULUM:" + PROGRAM + ":COURSE:" + code,
                                     "course_code": code, "name": code, "curriculum_id": PROGRAM,
                                     "round": 2, "total_credits": 6, "theory_credits": 1, "practice_credits": 5}})
    # One concept cited in two selected chapters and an excluded chapter.
    nodes.append({"element_id": "clinical", "labels": ["MedicalConcept", "Condition"],
                  "properties": {"id": "clinical-id", "name": "Synthetic source node", "content": [{
                      "sources": [
                          {"source_id": "SRC_ORTHO_TEXTBOOK_001", "pdf_pages": [254, 269], "locator_id": "loc-19"},
                          {"source_id": "SRC_ORTHO_EMERGENCY_001", "pdf_pages": [89], "locator_id": "loc-15"},
                          {"source_id": "SRC_ORTHO_TEXTBOOK_001", "pdf_pages": [117], "locator_id": "excluded-burns"},
                          {"source_id": "OTHER_BOOK", "pdf_pages": [254], "locator_id": "wrong-book"},
                          {"source_id": "SRC_ORTHO_TEXTBOOK_001", "pdf_pages": [True, "254"], "locator_id": "invalid-page"},
                      ]}]}})
    # Same page number from an unrelated book must never create membership.
    nodes.append({"element_id": "unrelated", "labels": ["MedicalConcept", "Condition"],
                  "properties": {"id": "unrelated-id", "sources": [{"source_id": "OTHER_BOOK", "pdf_pages": [254]}]}})
    return spec, catalog, {"nodes": nodes, "relationships": []}


def materialized(graph, snapshot):
    result = copy.deepcopy(snapshot)
    for i, n in enumerate(graph["nodes"]):
        result["nodes"].append({"element_id": "new-node-" + str(i), **copy.deepcopy(n)})
    elements = {n["properties"]["id"]: n["element_id"] for n in result["nodes"]}
    for i, e in enumerate(graph["edges"]):
        result["relationships"].append({"element_id": "new-edge-" + str(i), "type": e["type"],
                                        "start_node": elements[e["from_id"]], "end_node": elements[e["to_id"]],
                                        "properties": copy.deepcopy(e["properties"])})
    return result


class Round2MappingTests(unittest.TestCase):
    def setUp(self):
        self.spec, self.catalog, self.before = fixture()
        self.graph = build_graph(self.spec, self.catalog, self.before)

    def test_only_four_courses_and_unique_shared_chapters(self):
        plans = [n for n in self.graph["nodes"] if n["labels"] == ["CourseStudyPlan"]]
        self.assertEqual({n["properties"]["course_code"] for n in plans}, {"B21CN7", "B21CN8", "B21CN9", "B21CN10"})
        chapter_ids = [n["properties"]["id"] for n in self.graph["nodes"] if n["labels"] == ["StudyChapter"]]
        self.assertEqual(len(chapter_ids), len(set(chapter_ids)))
        shared = MANAGER + ":CHAPTER:SRC_ORTHO_TEXTBOOK_001:19"
        uses = [e for e in self.graph["edges"] if e["type"] == "HAS_READING" and e["to_id"] == shared]
        self.assertEqual(len(uses), 2)

    def test_membership_requires_book_and_exact_pdf_pages(self):
        edges = [e for e in self.graph["edges"] if e["type"] == "HAS_EXTRACTED_NODE"]
        self.assertEqual(len(edges), 2)
        self.assertEqual({e["to_id"] for e in edges}, {"clinical-id"})
        locators = {loc for e in edges for loc in e["properties"]["locator_ids"]}
        self.assertEqual(locators, {"loc-19", "loc-15"})
        primary = next(e for e in edges if e["properties"]["source_id"] == "SRC_ORTHO_TEXTBOOK_001")
        self.assertEqual(primary["properties"]["pdf_pages"], [254, 269])

    def test_reapply_is_idempotent_and_preserves_all_originals(self):
        after = materialized(self.graph, self.before)
        verify_preserved(self.before, after)
        self.assertEqual(plan_changes(self.graph, after), {"nodes": [], "edges": []})
        self.assertEqual(build_graph(self.spec, self.catalog, after), self.graph)

    def test_refuses_overwriting_existing_node_or_relation(self):
        for target in ("nodes", "relationships"):
            after = materialized(self.graph, self.before)
            after[target][-1]["properties"]["unmanaged_change"] = True
            with self.assertRaisesRegex(ValueError, "conflict"):
                plan_changes(self.graph, after)

    def test_verification_detects_original_content_edit_or_deletion(self):
        after = copy.deepcopy(self.before)
        after["nodes"][-1]["properties"]["sources"] = []
        with self.assertRaisesRegex(ValueError, "existing_graph_modified"):
            verify_preserved(self.before, after)
        after = copy.deepcopy(self.before)
        after["nodes"].pop()
        with self.assertRaisesRegex(ValueError, "existing_graph_modified"):
            verify_preserved(self.before, after)

    def test_rejects_elective_and_false_official_claims(self):
        for change in ("elective", "official_syllabus_confirmed", "practice_credit_awarded", "clinical_currency_verified"):
            spec = copy.deepcopy(self.spec)
            if change == "elective":
                spec["courses"][0]["course_code"] = "B21CN11"
            else:
                spec[change] = True
            with self.assertRaises(ValueError):
                build_graph(spec, self.catalog, self.before)

    def test_missing_or_wrong_course_metadata_aborts(self):
        for change in ("duplicate", "credits", "missing"):
            before = copy.deepcopy(self.before)
            if change == "duplicate":
                before["nodes"].append(copy.deepcopy(before["nodes"][0]))
            elif change == "credits":
                before["nodes"][0]["properties"]["practice_credits"] = 0
            else:
                before["nodes"].pop(0)
            with self.assertRaises(ValueError):
                build_graph(self.spec, self.catalog, before)

    def test_duplicate_chapter_and_invalid_page_bounds_abort(self):
        spec = copy.deepcopy(self.spec)
        spec["courses"][0]["readings"][0]["chapters"].append(1)
        with self.assertRaisesRegex(ValueError, "duplicate_course_chapter"):
            build_graph(spec, self.catalog, self.before)
        catalog = copy.deepcopy(self.catalog)
        for book in catalog["books"]:
            if book["year"] == 2021:
                next(c for c in book["chapters"] if c["number"] == 19)["end"] = 999
        with self.assertRaisesRegex(ValueError, "invalid_chapter_page_range"):
            build_graph(self.spec, catalog, self.before)

    def test_gap_and_source_quality_status_remain_explicit(self):
        plans = [n["properties"] for n in self.graph["nodes"] if n["labels"] == ["CourseStudyPlan"]]
        joint = next(n for n in plans if n["course_code"] == "B21CN9")
        self.assertEqual(joint["coverage_status"], "partial_joint_trauma_only")
        self.assertTrue(joint["pending_confirmation"])
        self.assertTrue(all(p["official_syllabus_confirmed"] is False and p["practice_credit_awarded"] is False for p in plans))
        self.assertEqual(len(self.graph["summary"]["chapters_with_source_opening_missing"]), 3)
        for course in plans:
            orders = [e["properties"]["display_order"] for e in self.graph["edges"]
                      if e["type"] == "HAS_READING" and e["from_id"] == course["id"]]
            self.assertEqual(orders, list(range(1, len(orders) + 1)))

    def test_citation_scan_does_not_mutate_original_source_list(self):
        props = {"sources": [{"source_id": "a"}], "content": [{"sources": [{"source_id": "b"}]}]}
        original = copy.deepcopy(props)
        citations(props)
        self.assertEqual(props, original)


if __name__ == "__main__":
    unittest.main()
