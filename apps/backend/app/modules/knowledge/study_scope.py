"""Product scope, kept separate from the complete source curriculum in Neo4j."""

import json
from pathlib import Path


def resident_study_scope() -> dict:
    profile = json.loads(
        Path(__file__).with_name("residency_scope.json").read_text(encoding="utf-8")
    )
    groups = profile["groups"]
    codes = [course["course_code"] for group in groups for course in group["courses"]]
    if len(codes) != len(set(codes)):
        raise ValueError("Duplicate course in resident study scope")
    if sum(g["required_credits"] for g in groups) != profile["total_required_credits"]:
        raise ValueError("Resident study credits do not match")
    for group in groups:
        if not 0 < group["choose"] <= group["offered"] == len(group["courses"]):
            raise ValueError("Invalid study scope selection rule")
    return profile
