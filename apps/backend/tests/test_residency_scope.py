import copy
import json
from pathlib import Path

from app.modules.knowledge.service import Snapshot
from app.modules.knowledge.study_scope import resident_study_scope
from tests.knowledge_fixture import COURSE, FOCUS_COURSE, SOURCE, make_snapshot

REPO = Path(__file__).resolve().parents[3]


def test_image_scope_credits_and_round_three_selection():
    profile = resident_study_scope()
    groups = profile["groups"]
    codes = [c["course_code"] for g in groups for c in g["courses"]]
    assert set(codes) == {f"B21CN{n}" for n in range(7, 19)}
    assert len(codes) == 12
    assert [(g["round"], g["choose"], g["offered"], g["required_credits"]) for g in groups] == [
        (2, 4, 4, 24),
        (3, 4, 8, 16),
    ]
    assert profile["total_required_credits"] == 40
    assert profile["total_required_theory_credits"] == 4
    assert profile["total_required_practice_credits"] == 36
    assert sum(c["total_credits"] for g in groups for c in g["courses"]) == 56
    assert profile["prior_course_policy"]["individual_completion"] == "not_assessed"
    assert profile["prior_course_policy"]["detailed_lessons"] is False
    assert profile["prior_course_policy"]["program_outcomes_are_course_outcomes"] is False


def test_prior_course_has_no_lesson_suggestions_and_snapshot_is_unchanged():
    snapshot = make_snapshot()
    snapshot.coverage = {
        "courses": [
            {
                "course_id": code,
                "topics": [{"topic_name": "Reference topic", "source_links": [SOURCE]}],
            }
            for code in ("B21CN1", "B21CN7")
        ]
    }
    before_nodes, before_edges = copy.deepcopy(snapshot.nodes), copy.deepcopy(snapshot.edges)
    result = snapshot.curriculum()
    courses = {n["id"]: n for n in result["nodes"] if n["type"] == "Course"}
    assert courses[COURSE]["study_role"] == "prior_outcomes_only"
    assert courses[COURSE]["suggested_topics"] == []
    assert courses[FOCUS_COURSE]["study_role"] == "focus"
    assert courses[FOCUS_COURSE]["suggested_topics"][0]["status"] == "provisional"
    assert courses[COURSE]["course_outcomes_status"] == "awaiting_teacher_confirmation"
    assert "learning_outcomes" not in courses[COURSE]
    assert snapshot.nodes == before_nodes and snapshot.edges == before_edges
    assert snapshot.search()["total"] == 2


def test_full_curriculum_keeps_all_courses_but_focuses_only_twelve():
    data = REPO / "data"
    graph = json.loads(
        (data / "knowledge-extraction/hmu-public-20261104/graph.json").read_text(encoding="utf-8")
    )
    catalog = json.loads((data / "library/catalog.json").read_text(encoding="utf-8"))
    nodes = [
        {"labels": ["CurriculumEntity", n["type"]], "p": n["properties"]} for n in graph["nodes"]
    ]
    edges = [
        {"start": e["from_id"], "end": e["to_id"], "type": e["type"], "p": e["properties"]}
        for e in graph["edges"]
    ]
    snapshot = Snapshot(nodes, edges, catalog, {"courses": []})
    result = snapshot.curriculum()
    courses = [n for n in result["nodes"] if n["type"] == "Course"]
    assert len(courses) == 27
    assert sum(n["study_role"] == "focus" for n in courses) == 12
    assert sum(n["study_role"] == "prior_outcomes_only" for n in courses) == 15
    assert len(snapshot.nodes) == 82 and len(snapshot.edges) == 145
    focused = {
        n["metadata"]["course_code"]: n["metadata"] for n in courses if n["study_role"] == "focus"
    }
    for group in result["study_scope"]["groups"]:
        for course in group["courses"]:
            for key in ("round", "year", "total_credits", "theory_credits", "practice_credits"):
                assert focused[course["course_code"]][key] == course[key]
