"""Transactional repair restricted to the previously imported 2021 book scope."""

import argparse
import copy
import json
import re
from collections import Counter

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.contracts import TYPES
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import validate_locators
from knowledge_pipeline.neo4j_export import read_graph
from scripts.complete_2021_book import OUT, PREVIOUS, ROOT
from scripts.finalize_2021_book import verify_protected

MANAGED = {
    "id",
    "name",
    "aliases",
    "kind",
    "text",
    "format",
    "options",
    "answer",
    "explanation",
    "content",
    "sources",
    "answer_sources",
}
BOOK_ID = "benh-hoc-ngoai-khoa-chan-thuong-chinh-hinh-2021"
REVIEW_METADATA = {
    "kg_book_id": BOOK_ID,
    "kg_review_run": OUT.name,
    "kg_review_status": "source_reviewed_draft",
    "kg_expert_verified": False,
}


def index_unique(rows):
    result = {}
    for row in rows:
        identifier = row["properties"].get("id")
        if identifier:
            if identifier in result:
                raise ValueError("existing_nonunique_id")
            result[identifier] = row
    return result


def repair_plan(graph, current, baseline, old_graph, chapter_by_id=None):
    """Pure preflight: foreign collisions and foreign incident edges are refused."""
    payload = dry_run_loader(graph)
    old_nodes = {n["id"] for n in old_graph["nodes"]}
    old_edges = {e["id"] for e in old_graph["edges"]}
    nodes = index_unique(current["nodes"])
    edges = index_unique(current["relationships"])
    baseline_nodes = index_unique(baseline["nodes"])
    baseline_edges = index_unique(baseline["relationships"])
    for identifiers, actual, expected in [
        (old_nodes, nodes, baseline_nodes),
        (old_edges, edges, baseline_edges),
    ]:
        for identifier in identifiers:
            if identifier not in actual or actual[identifier] != expected[identifier]:
                raise ValueError("previously_imported_book_changed_since_snapshot")
    owned_elements = {nodes[k]["element_id"] for k in old_nodes}
    for edge in current["relationships"]:
        if (
            edge["start_node"] in owned_elements or edge["end_node"] in owned_elements
        ) and edge["properties"].get("id") not in old_edges:
            raise ValueError("foreign_relationship_touches_owned_book")
    planned_nodes = []
    for row in payload["nodes"]:
        identifier = row["properties"]["id"]
        previous = nodes.get(identifier)
        if previous and identifier not in old_nodes:
            raise ValueError("foreign_node_identity_collision")
        props = (
            {
                k: copy.deepcopy(v)
                for k, v in previous["properties"].items()
                if k not in MANAGED
            }
            if previous
            else {}
        )
        props.update(row["properties"])
        props.update(REVIEW_METADATA)
        if chapter_by_id is not None:
            props["kg_chapter"] = chapter_by_id[identifier]
        labels = sorted(
            (
                set(previous["labels"]) - set(TYPES) - {"MedicalConcept"}
                if previous
                else set()
            )
            | set(row["labels"])
        )
        if not set(labels) <= set(TYPES) | {"MedicalConcept"}:
            raise ValueError("unexpected_owned_labels_require_review")
        if previous and "MedResidentDemo" in previous["labels"]:
            raise ValueError("demo_data_cannot_be_repaired_as_book")
        action = (
            "create"
            if previous is None
            else "skip"
            if props == previous["properties"] and labels == sorted(previous["labels"])
            else "update"
        )
        planned_nodes.append(
            {
                "properties": props,
                "labels": labels,
                "before": previous,
                "action": action,
            }
        )
    for row in payload["edges"]:
        if row["properties"]["id"] in edges:
            raise ValueError("new_edge_identity_collision")
        row["properties"].update(REVIEW_METADATA)
        if chapter_by_id is not None:
            row["properties"]["kg_chapter"] = chapter_by_id[row["from_id"]]
    final_ids = {n["id"] for n in graph["nodes"]}
    return {
        "nodes": planned_nodes,
        "edges": payload["edges"],
        "delete_edges": [edges[k] for k in sorted(old_edges)],
        "delete_nodes": [nodes[k] for k in sorted(old_nodes - final_ids)],
        "scope_node_elements": sorted(owned_elements),
        "scope_edge_elements": sorted(edges[k]["element_id"] for k in old_edges),
        "counts": {
            "nodes": dict(Counter(n["action"] for n in planned_nodes)),
            "create_edges": len(payload["edges"]),
            "delete_edges": len(old_edges),
            "delete_nodes": len(old_nodes - final_ids),
        },
    }


def write_repair(tx, plan):
    # Values are parameterized. Label and relationship strings originate only
    # from the closed contracts validated by dry_run_loader.
    if plan["delete_edges"]:
        tx.run(
            "MATCH ()-[r]->() WHERE elementId(r) IN $ids DELETE r",
            ids=[r["element_id"] for r in plan["delete_edges"]],
        ).consume()
    for row in plan["nodes"]:
        if row["action"] == "skip":
            continue
        labels = ":".join(row["labels"])
        if row["before"]:
            remove = sorted(set(row["before"]["labels"]) - set(row["labels"]))
            query = "MATCH (n) WHERE elementId(n)=$element SET n=$props "
            if remove:
                query += "REMOVE n:" + ":".join(remove) + " "
            query += "SET n:" + labels
            tx.run(
                query, element=row["before"]["element_id"], props=row["properties"]
            ).consume()
        else:
            tx.run(
                f"CREATE (n:{labels}) SET n=$props", props=row["properties"]
            ).consume()
    for row in plan["edges"]:
        tx.run(
            "MATCH (a {id:$left}), (b {id:$right}) "
            f"CREATE (a)-[r:{row['type']}]->(b) SET r=$props",
            left=row["from_id"],
            right=row["to_id"],
            props=row["properties"],
        ).consume()
    if plan["delete_nodes"]:
        # DELETE refuses any remaining incident relationship; never DETACH DELETE.
        tx.run(
            "MATCH (n) WHERE elementId(n) IN $ids DELETE n",
            ids=[r["element_id"] for r in plan["delete_nodes"]],
        ).consume()


def verify_snapshot(before, after, plan):
    new_nodes = index_unique(after["nodes"])
    new_edges = index_unique(after["relationships"])
    elements = {n["element_id"]: n["properties"].get("id") for n in after["nodes"]}
    for row in plan["nodes"]:
        found = new_nodes[row["properties"]["id"]]
        if (
            sorted(found["labels"]) != sorted(row["labels"])
            or found["properties"] != row["properties"]
        ):
            raise ValueError("scoped_node_readback_mismatch")
    for row in plan["edges"]:
        found = new_edges[row["properties"]["id"]]
        if found["properties"] != row["properties"] or (
            elements[found["start_node"]],
            found["type"],
            elements[found["end_node"]],
        ) != (row["from_id"], row["type"], row["to_id"]):
            raise ValueError("scoped_edge_readback_mismatch")
    for key, scoped in [
        ("nodes", set(plan["scope_node_elements"])),
        ("relationships", set(plan["scope_edge_elements"])),
    ]:
        actual = {r["element_id"]: r for r in after[key]}
        for row in before[key]:
            if row["element_id"] not in scoped and actual.get(row["element_id"]) != row:
                raise ValueError("outside_book_data_changed")
    for row in plan["delete_nodes"]:
        if row["properties"]["id"] in new_nodes:
            raise ValueError("obsolete_owned_node_still_present")
    for row in plan["delete_edges"]:
        if row["properties"]["id"] in new_edges:
            raise ValueError("obsolete_owned_relationship_still_present")
    expected_nodes = (
        len(before["nodes"])
        + sum(r["action"] == "create" for r in plan["nodes"])
        - len(plan["delete_nodes"])
    )
    expected_edges = (
        len(before["relationships"]) + len(plan["edges"]) - len(plan["delete_edges"])
    )
    if (len(after["nodes"]), len(after["relationships"])) != (
        expected_nodes,
        expected_edges,
    ):
        raise ValueError("unexpected_database_counts_after_scoped_repair")
    return {
        "outside_nodes_unchanged": len(before["nodes"])
        - len(plan["scope_node_elements"]),
        "outside_relationships_unchanged": len(before["relationships"])
        - len(plan["scope_edge_elements"]),
        "book_nodes_verified": len(plan["nodes"]),
        "book_edges_verified": len(plan["edges"]),
        "total_nodes": len(after["nodes"]),
        "total_relationships": len(after["relationships"]),
    }


def idempotent_check(current, plan, before):
    verification = verify_snapshot(before, current, plan)
    expected_nodes = index_unique(current["nodes"])
    expected_edges = index_unique(current["relationships"])
    if any(
        expected_nodes[n["properties"]["id"]]["properties"] != n["properties"]
        for n in plan["nodes"]
    ):
        raise ValueError("non_idempotent_nodes")
    if any(
        expected_edges[e["properties"]["id"]]["properties"] != e["properties"]
        for e in plan["edges"]
    ):
        raise ValueError("non_idempotent_relationships")
    return {**verification, "idempotent": True, "writes_needed": 0}


def run(apply=False):
    from dotenv import dotenv_values
    from neo4j import GraphDatabase

    graph = read_json(OUT / "combined/graph.json")
    summary = read_json(OUT / "review-summary.json")
    if fingerprint(graph) != summary["graph_fingerprint"]:
        raise ValueError("compiled_graph_changed")
    for path in ["node-resolution.json", "edge-resolution.json"]:
        if read_json(OUT / "audit" / path)["faults"]:
            raise ValueError("unresolved_review_faults")
    if read_json(OUT / "audit/source-attention.json"):
        raise ValueError("unresolved_source_review")
    locator_count = validate_locators(graph, OUT / "combined")
    protected = verify_protected()
    config = dotenv_values(ROOT / ".env", interpolate=False)
    folder = OUT / "imports/completion"
    manifest_file = folder / "apply-manifest.json"
    with (
        GraphDatabase.driver(
            config["NEO4J_URI"],
            auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
            connection_timeout=10,
            max_transaction_retry_time=0,
        ) as driver,
        driver.session(database=config["NEO4J_DATABASE"]) as session,
    ):
        with session.begin_transaction(timeout=300) as tx:
            before = read_graph(tx, None)
            if manifest_file.exists():
                manifest = read_json(manifest_file)
                if manifest["status"] != "imported_and_verified" or manifest[
                    "graph_fingerprint"
                ] != fingerprint(graph):
                    raise ValueError("existing_import_audit_requires_diagnosis")
                check = idempotent_check(
                    before,
                    read_json(folder / "repair-plan.json"),
                    read_json(folder / "before-all.json"),
                )
                write_json(folder / "idempotency.json", check)
                print(json.dumps(check), flush=True)
                return check
            node_state = read_json(OUT / "audit/node-resolution.json")
            owners = {
                r["key"]: r["chapter"]
                for r in read_json(OUT / "audit/proposals.json")["nodes"]
            }
            chapter_by_id = {n["id"]: owners[k] for k, n in node_state["nodes"].items()}
            plan = repair_plan(
                graph,
                before,
                read_json(OUT / "audit/neo4j-before-all.json"),
                read_json(PREVIOUS / "combined/graph.json"),
                chapter_by_id,
            )
            write_json(folder / "repair-plan.json", plan)
            write_json(folder / "before-all.json", before)
            preview = {
                "status": "preflight_passed",
                "graph_fingerprint": fingerprint(graph),
                "counts": plan["counts"],
                "protected_files_unchanged": protected,
                "locators_verified": locator_count,
            }
            write_json(folder / "preflight.json", preview)
            if not apply:
                print(json.dumps(preview), flush=True)
                return preview
            # The file prevents a process interruption from masquerading as a
            # safely retryable apply. A resumed call must inspect actual state.
            write_json(
                manifest_file,
                {"status": "applying", "graph_fingerprint": fingerprint(graph)},
            )
            write_repair(tx, plan)
            after = read_graph(tx, None)
            verification = verify_snapshot(before, after, plan)
            write_json(folder / "transaction-preview.json", after)
            tx.commit()
        with session.begin_transaction(timeout=60) as tx:
            after = read_graph(tx, None)
            verification = verify_snapshot(before, after, plan)
            tx.commit()
    manifest = {
        **preview,
        **verification,
        "status": "imported_and_verified",
        "expert_verified": False,
    }
    write_json(folder / "after-all.json", after)
    write_json(manifest_file, manifest)
    check = idempotent_check(after, plan, before)
    write_json(folder / "idempotency.json", check)
    write_json(OUT / "audit/final-database-verification.json", {**manifest, **check})
    print(json.dumps(manifest), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(args.apply)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- no credential-bearing tracebacks
        reason = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch("[A-Za-z_]+", str(exc))
            else None
        )
        print(
            json.dumps(
                {"status": "failed", "error_type": type(exc).__name__, "reason": reason}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
