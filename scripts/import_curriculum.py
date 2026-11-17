"""Import the full course tree using the verified curriculum subset's identities.

Preview: python -m scripts.import_curriculum
Import:  python -m scripts.import_curriculum --apply
Existing course identities, teacher content and data outside Curriculum are preserved.
Only the previous flat group links and managed curriculum metadata are migrated.
"""

import argparse
import copy
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from document_toolkit.common import read_json, validate_schema, write_json
from knowledge_pipeline.neo4j_export import read_graph

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/curriculum/curriculum_map.json"
TREE_SOURCE = ROOT / "data/curriculum/curriculum_tree.json"
OUTPUT = ROOT / "data/curriculum/neo4j"
LABELS = {"Curriculum", "CurriculumGroup", "Course", "CurriculumRequirement"}
RELATIONS = {"HAS_GROUP", "HAS_COURSE", "HAS_REQUIREMENT"}
PENDING = "awaiting_teacher_content"


def metadata(value, excluded=()):
    result = {}
    for key, item in value.items():
        if key in excluded or item is None:
            continue
        if isinstance(item, (dict, list)):
            result[key + "_json"] = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            result[key] = item
    return result


def build_skeleton(source):
    validate_schema(source, read_json(SOURCE.with_suffix(".schema.json")))
    program = source["program"]
    program_id = program["program_id"]
    root_id = "CURRICULUM:" + program_id
    base = {"curriculum_id": program_id}
    nodes = [
        {
            "type": "Curriculum",
            "properties": {
                **metadata(program),
                **base,
                "id": root_id,
                "name": program["program_name"],
                "source_path": SOURCE.relative_to(ROOT).as_posix(),
                "scope_json": json.dumps(
                    source["scope"], ensure_ascii=False, sort_keys=True
                ),
            },
        }
    ]
    edges, codes, groups = [], set(), set()
    for group_order, group in enumerate(source["course_groups"], 1):
        gid = group["group_id"]
        if gid in groups:
            raise ValueError("duplicate_curriculum_group")
        groups.add(gid)
        group_id = root_id + ":GROUP:" + gid
        nodes.append(
            {
                "type": "CurriculumGroup",
                "properties": {
                    **metadata(group, ["courses"]),
                    **base,
                    "id": group_id,
                    "name": group["group_name"],
                    "display_order": group_order,
                },
            }
        )
        edges.append({"type": "HAS_GROUP", "from_id": root_id, "to_id": group_id})
        for course_order, course in enumerate(group["courses"], 1):
            code = course["course_code"]
            if code in codes:
                raise ValueError("duplicate_course_code")
            codes.add(code)
            if course["round"] != group["round"]:
                raise ValueError("course_round_mismatches_group")
            if (
                course["total_credits"]
                != course["theory_credits"] + course["practice_credits"]
            ):
                raise ValueError("course_credit_mismatch")
            course_id = root_id + ":COURSE:" + code
            # Only course identity and curriculum metadata belong in this skeleton.
            props = metadata(
                course, ["content_outline", "learning_outcomes", "prerequisites"]
            )
            nodes.append(
                {
                    "type": "Course",
                    "properties": {
                        **props,
                        **base,
                        "id": course_id,
                        "name": course["course_name"],
                        "curriculum_group_id": gid,
                        "display_order": course_order,
                    },
                }
            )
            edges.append(
                {"type": "HAS_COURSE", "from_id": group_id, "to_id": course_id}
            )
        selection = group.get("selection_rule")
        if isinstance(selection, dict) and selection.get("type") == "choose_n_of_m":
            if (
                selection["from"] != len(group["courses"])
                or not 0 < selection["choose"] <= selection["from"]
            ):
                raise ValueError("invalid_elective_selection")
            if (
                group["total_credits_required"]
                != selection["choose"] * selection["credits_per_course"]
            ):
                raise ValueError("elective_required_credits_mismatch")
        elif "total_credits" in group and group["total_credits"] != sum(
            c["total_credits"] for c in group["courses"]
        ):
            raise ValueError("group_credit_mismatch")
    for edge in edges:
        edge["properties"] = {
            **base,
            "id": edge["from_id"] + ":" + edge["type"] + ":" + edge["to_id"],
        }
    return {
        "format": "medresident-curriculum-skeleton-v1",
        "curriculum_id": program_id,
        "nodes": nodes,
        "edges": edges,
    }


def index_unique(rows):
    result = {}
    for row in rows:
        key = row["properties"].get("id")
        if key:
            if key in result:
                raise ValueError("duplicate_existing_graph_id")
            result[key] = row
    return result


def build_curriculum_tree(tree, legacy):
    """Use the user's full list while retaining the verified subset's identities."""
    if tree.get("format") != "medresident-curriculum-tree-v1":
        raise ValueError("unsupported_curriculum_tree_format")
    graph = {
        **legacy,
        "format": "medresident-curriculum-skeleton-v2",
        "nodes": [],
        "edges": [],
    }
    program_id = legacy["curriculum_id"]
    root = copy.deepcopy(next(n for n in legacy["nodes"] if n["type"] == "Curriculum"))
    root_id = root["properties"]["id"]
    root["properties"].update(
        source_path=TREE_SOURCE.relative_to(ROOT).as_posix(),
        source_scope="Danh sách đầy đủ do người dùng cung cấp: kiến thức chung, cơ sở hỗ trợ và chuyên ngành; metadata 13 học phần CTCH kế thừa từ ảnh chương trình đã cung cấp.",
        listing_sources_json=json.dumps(
            tree["source_records"], ensure_ascii=False, sort_keys=True
        ),
    )
    graph["nodes"].append(root)
    old_groups = {
        n["properties"]["group_id"]: n
        for n in legacy["nodes"]
        if n["type"] == "CurriculumGroup"
    }
    old_courses = {
        n["properties"]["course_code"]: n
        for n in legacy["nodes"]
        if n["type"] == "Course"
    }
    group_ids = [g["group_id"] for g in tree["course_groups"]]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("duplicate_curriculum_group")
    parents = {g["group_id"]: g["parent_group_id"] for g in tree["course_groups"]}
    for gid in group_ids:
        visited, current = set(), gid
        while current is not None:
            if current in visited or current not in parents:
                raise ValueError("invalid_curriculum_parent_or_cycle")
            visited.add(current)
            current = parents[current]

    def group_key(gid):
        return root_id + ":GROUP:" + gid if gid is not None else root_id

    def edge(kind, left, right):
        graph["edges"].append(
            {
                "type": kind,
                "from_id": left,
                "to_id": right,
                "properties": {
                    "curriculum_id": program_id,
                    "id": left + ":" + kind + ":" + right,
                },
            }
        )

    sibling_orders, course_keys = {}, set()
    for group in tree["course_groups"]:
        gid, parent = group["group_id"], group["parent_group_id"]
        sibling_orders[parent] = sibling_orders.get(parent, 0) + 1
        props = copy.deepcopy(old_groups.get(gid, {}).get("properties", {}))
        props.update(metadata(group, ["courses", "parent_group_id"]))
        props.update(
            id=group_key(gid),
            curriculum_id=program_id,
            name=group["group_name"],
            display_order=sibling_orders[parent],
        )
        selection = group.get("selection_rule")
        if selection:
            if (
                selection["from"] != len(group["courses"])
                or not 0 < selection["choose"] <= selection["from"]
            ):
                raise ValueError("invalid_elective_selection")
            props.update(
                selection_choose=selection["choose"], selection_from=selection["from"]
            )
        graph["nodes"].append({"type": "CurriculumGroup", "properties": props})
        edge("HAS_GROUP", group_key(parent), group_key(gid))
        for order, course in enumerate(group["courses"], 1):
            code = course.get("course_code")
            if code and not course.get("internal_key"):
                if code not in old_courses:
                    raise ValueError("unknown_official_course_code")
                node = copy.deepcopy(old_courses[code])
                key = code
            else:
                key = "INTERNAL:" + course["internal_key"]
                node = {
                    "type": "Course",
                    "properties": {
                        **metadata(course),
                        "id": root_id + ":COURSE:" + key,
                        "curriculum_id": program_id,
                        "name": course["course_name"],
                        "course_code_status": course.get(
                            "course_code_status", "not_provided"
                        ),
                        "source_status": "listed_in_user_provided_curriculum",
                    },
                }
                if "round" in group:
                    node["properties"]["round"] = group["round"]
                if "course_type" in group:
                    node["properties"]["course_type"] = group["course_type"]
            if key in course_keys:
                raise ValueError("duplicate_course_identity")
            course_keys.add(key)
            node["properties"].update(curriculum_group_id=gid, display_order=order)
            graph["nodes"].append(node)
            edge("HAS_COURSE", group_key(gid), node["properties"]["id"])
    for item in tree.get("requirements", []):
        if item["parent_group_id"] not in parents:
            raise ValueError("unknown_requirement_parent")
        identifier = root_id + ":REQUIREMENT:" + item["requirement_id"]
        graph["nodes"].append(
            {
                "type": "CurriculumRequirement",
                "properties": {
                    **metadata(item, ["parent_group_id"]),
                    "id": identifier,
                    "curriculum_id": program_id,
                    "status": "not_assessed",
                },
            }
        )
        edge("HAS_REQUIREMENT", group_key(item["parent_group_id"]), identifier)
    if len({n["properties"]["id"] for n in graph["nodes"]}) != len(graph["nodes"]):
        raise ValueError("duplicate_curriculum_node_identity")
    return graph


def build_plan(graph, before, previous_graph=None):
    nodes = index_unique(before["nodes"])
    edges = index_unique(before["relationships"])
    elements = {n["element_id"]: n["properties"].get("id") for n in before["nodes"]}
    prior_nodes = {
        n["properties"]["id"]: n for n in (previous_graph or {}).get("nodes", [])
    }
    create_nodes, create_edges, update_nodes, delete_edges = [], [], [], []
    for node in graph["nodes"]:
        old = nodes.get(node["properties"]["id"])
        if old is None:
            create_nodes.append(node)
        elif (
            not {"CurriculumEntity", node["type"]} <= set(old["labels"])
            or "MedicalConcept" in old["labels"]
        ):
            raise ValueError("curriculum_id_collision_with_other_data")
        else:
            changes = {
                k: v
                for k, v in node["properties"].items()
                if old["properties"].get(k) != v
            }
            if changes:
                prior = prior_nodes.get(node["properties"]["id"])
                if prior is None or any(
                    old["properties"].get(k) != prior["properties"].get(k)
                    for k in changes
                ):
                    raise ValueError("existing_curriculum_metadata_differs")
                update_nodes.append(
                    {"element_id": old["element_id"], "changes": changes}
                )
    for edge in graph["edges"]:
        old = edges.get(edge["properties"]["id"])
        if old is None:
            create_edges.append(edge)
        elif (elements[old["start_node"]], old["type"], elements[old["end_node"]]) != (
            edge["from_id"],
            edge["type"],
            edge["to_id"],
        ) or any(old["properties"].get(k) != v for k, v in edge["properties"].items()):
            raise ValueError("existing_curriculum_relationship_differs")
    desired_ids = {e["properties"]["id"] for e in graph["edges"]}
    for edge in (previous_graph or {}).get("edges", []):
        identifier = edge["properties"]["id"]
        old = edges.get(identifier)
        if identifier not in desired_ids and old:
            if old["properties"] != edge["properties"] or (
                elements[old["start_node"]],
                old["type"],
                elements[old["end_node"]],
            ) != (edge["from_id"], edge["type"], edge["to_id"]):
                raise ValueError("old_curriculum_relationship_changed")
            delete_edges.append(old)
    return {
        "create_nodes": create_nodes,
        "create_edges": create_edges,
        "nodes_to_create": len(create_nodes),
        "edges_to_create": len(create_edges),
        "update_nodes": update_nodes,
        "delete_edges": delete_edges,
        "nodes_to_update": len(update_nodes),
        "edges_to_delete": len(delete_edges),
    }


def verify_graph(graph, before, after, plan, previous_graph=None):
    updates = {r["element_id"]: r["changes"] for r in plan.get("update_nodes", [])}
    deleted = {r["element_id"] for r in plan.get("delete_edges", [])}
    for kind in ["nodes", "relationships"]:
        actual = {r["element_id"]: r for r in after[kind]}
        for row in before[kind]:
            if kind == "relationships" and row["element_id"] in deleted:
                continue
            expected = copy.deepcopy(row)
            if kind == "nodes":
                expected["properties"].update(updates.get(row["element_id"], {}))
            if actual.get(row["element_id"]) != expected:
                raise ValueError("preexisting_graph_data_changed")
    after_edges = index_unique(after["relationships"])
    if any(r["properties"]["id"] in after_edges for r in plan.get("delete_edges", [])):
        raise ValueError("obsolete_curriculum_relationship_remains")
    remaining = build_plan(graph, after, previous_graph)
    if any(
        remaining[k]
        for k in [
            "nodes_to_create",
            "edges_to_create",
            "nodes_to_update",
            "edges_to_delete",
        ]
    ):
        raise ValueError("curriculum_readback_incomplete")
    if len(after["nodes"]) != len(before["nodes"]) + plan["nodes_to_create"] or len(
        after["relationships"]
    ) != len(before["relationships"]) + plan["edges_to_create"] - plan.get(
        "edges_to_delete", 0
    ):
        raise ValueError("unexpected_graph_counts")
    return {
        "nodes_verified": len(graph["nodes"]),
        "relationships_verified": len(graph["edges"]),
        "preexisting_nodes_unchanged": len(before["nodes"]) - len(updates),
        "preexisting_relationships_unchanged": len(before["relationships"])
        - len(deleted),
        "non_curriculum_nodes_unchanged": sum(
            "CurriculumEntity" not in n["labels"] for n in before["nodes"]
        ),
        "non_curriculum_relationships_unchanged": sum(
            r["properties"].get("curriculum_id") != graph["curriculum_id"]
            for r in before["relationships"]
        ),
        "writes_needed_on_rerun": 0,
    }


def write_graph(tx, plan, allowed_labels=LABELS, allowed_relations=RELATIONS):
    for node in plan["create_nodes"]:
        if node["type"] not in allowed_labels:
            raise ValueError("unsupported_curriculum_label")
        initial = {"content_status": PENDING} if node["type"] == "Course" else {}
        tx.run(
            f"MERGE (n:CurriculumEntity:{node['type']} {{id:$id}}) ON CREATE SET n += $props, n += $initial",
            id=node["properties"]["id"],
            props=node["properties"],
            initial=initial,
        ).consume()
    for row in plan.get("update_nodes", []):
        tx.run(
            "MATCH (n:CurriculumEntity) WHERE elementId(n)=$element SET n += $changes",
            element=row["element_id"],
            changes=row["changes"],
        ).consume()
    for row in plan.get("delete_edges", []):
        tx.run(
            "MATCH ()-[r]->() WHERE elementId(r)=$element DELETE r",
            element=row["element_id"],
        ).consume()
    for edge in plan["create_edges"]:
        if edge["type"] not in allowed_relations:
            raise ValueError("unsupported_curriculum_relationship")
        tx.run(
            "MATCH (a:CurriculumEntity {id:$left}), (b:CurriculumEntity {id:$right}) "
            f"MERGE (a)-[r:{edge['type']} {{id:$id}}]->(b) ON CREATE SET r += $props",
            left=edge["from_id"],
            right=edge["to_id"],
            id=edge["properties"]["id"],
            props=edge["properties"],
        ).consume()


def run(apply=False):
    from dotenv import dotenv_values
    from neo4j import GraphDatabase

    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    legacy = build_skeleton(read_json(SOURCE))
    tree_hash = (
        hashlib.sha256(TREE_SOURCE.read_bytes()).hexdigest()
        if TREE_SOURCE.exists()
        else None
    )
    graph = (
        build_curriculum_tree(read_json(TREE_SOURCE), legacy) if tree_hash else legacy
    )
    write_json(OUTPUT / "graph.json", graph)
    (OUTPUT / "view.cypher").write_text(
        "// Neo4j Browser: show the complete curriculum tree.\n"
        'MATCH p=(c:Curriculum {curriculum_id:"' + graph["curriculum_id"] + '"})'
        "-[:HAS_GROUP|HAS_COURSE|HAS_REQUIREMENT*1..6]->(:CurriculumEntity) RETURN p;\n\n"
        "// List course codes, names and content status.\n"
        "MATCH (g:CurriculumGroup)-[:HAS_COURSE]->(s:Course) "
        'WHERE s.curriculum_id="' + graph["curriculum_id"] + '" '
        "RETURN g.name AS nhom, s.course_code AS ma_mon, s.name AS mon_hoc, "
        "s.content_status AS noi_dung ORDER BY g.display_order, s.display_order;\n",
        encoding="utf-8",
    )
    config = dotenv_values(ROOT / ".env", interpolate=False, encoding="utf-8-sig")
    required = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"]
    if any(not config.get(k) or config[k].startswith("<") for k in required):
        raise ValueError("missing_neo4j_configuration")
    backup = (
        ROOT
        / "data/backups/curriculum"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
    )
    with (
        GraphDatabase.driver(
            config["NEO4J_URI"],
            auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
            connection_timeout=5,
            connection_acquisition_timeout=10,
            max_transaction_retry_time=0,
        ) as driver,
        driver.session(database=config["NEO4J_DATABASE"]) as session,
    ):
        with session.begin_transaction(timeout=90) as tx:
            before = read_graph(tx, None)
            plan = build_plan(graph, before, legacy)
            report = {
                "status": "preflight_passed",
                "source_sha256": source_hash,
                "tree_source_sha256": tree_hash,
                "curriculum_nodes": len(graph["nodes"]),
                "curriculum_relationships": len(graph["edges"]),
                "courses": sum(n["type"] == "Course" for n in graph["nodes"]),
                "nodes_created": plan["nodes_to_create"],
                "relationships_created": plan["edges_to_create"],
                "nodes_updated": plan["nodes_to_update"],
                "relationships_deleted": plan["edges_to_delete"],
                "requirements": sum(
                    n["type"] == "CurriculumRequirement" for n in graph["nodes"]
                ),
            }
            if not apply:
                write_json(OUTPUT / "preflight.json", report)
                return report
            write_json(backup / "before-all.json", before)
            write_json(backup / "plan.json", plan)
            write_graph(tx, plan)
            after = read_graph(tx, None)
            verification = verify_graph(graph, before, after, plan, legacy)
            if (
                hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_hash
                or tree_hash
                and hashlib.sha256(TREE_SOURCE.read_bytes()).hexdigest() != tree_hash
            ):
                raise ValueError("curriculum_source_changed_during_import")
            tx.commit()
        with session.begin_transaction(timeout=60) as tx:
            after = read_graph(tx, None)
            verification = verify_graph(graph, before, after, plan, legacy)
    report.update(verification, status="imported_and_verified", source_unchanged=True)
    write_json(backup / "after-all.json", after)
    write_json(backup / "report.json", report)
    name = (
        "import-report.json"
        if any(
            plan[k]
            for k in [
                "nodes_to_create",
                "edges_to_create",
                "nodes_to_update",
                "edges_to_delete",
            ]
        )
        else "verification.json"
    )
    write_json(OUTPUT / name, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.apply), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 -- never print credential-bearing driver tracebacks
        reason = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc))
            else None
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_code": getattr(exc, "code", None),
                    "reason": reason,
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
