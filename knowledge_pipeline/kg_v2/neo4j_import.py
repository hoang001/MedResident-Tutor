"""Scoped source-reviewed graph upsert; no deletes, schema migrations or LLM calls."""

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import DEFAULT_ENV_FILE
from knowledge_pipeline.neo4j_export import read_graph

from .contracts import TYPES
from .loader import NESTED, dry_run_loader
from .validation import cycle_if_added


def merge_unique(left, right):
    result = copy.deepcopy(left)
    for item in right:
        if item not in result:
            result.append(copy.deepcopy(item))
    return result


def merge_content(left, right):
    """Keep statements distinct; merge sources only for exactly equal statement text."""
    result = copy.deepcopy(left)
    for item in right:
        same = next((c for c in result if c["text"] == item["text"]), None)
        if same is None:
            result.append(copy.deepcopy(item))
        else:
            same["sources"] = merge_unique(same["sources"], item["sources"])
    return result


def validate_locators(graph, review):
    pages = {
        (p["source_id"], p["pdf_page"]): p
        for p in map(
            json.loads,
            (review / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    locators = {r["locator_id"]: r for r in read_json(review / "audit/locators.json")}
    checked = set()
    for row in graph["nodes"] + graph["edges"]:
        refs = row.get("sources", []) + row.get("answer_sources", [])
        for c in row.get("content", []):
            if c["text"] != "\n".join(s["excerpt"] for s in c["sources"]):
                raise ValueError("review_content_not_exact_source")
            refs += c["sources"]
        for s in refs:
            loc = locators[s["locator_id"]]
            page = pages[(s["source_id"], loc["pdf_page"])]
            if (
                page["text"][loc["char_start"] : loc["char_end"]] != s["excerpt"]
                or page["raw_text"][loc["raw_char_start"] : loc["raw_char_end"]]
                != loc["raw_text"]
                or s["pdf_pages"] != [loc["pdf_page"]]
                or loc["source_id"] != s["source_id"]
            ):
                raise ValueError("review_locator_mismatch")
            checked.add(s["locator_id"])
    return len(checked)


def build_plan(graph, snapshot):
    """Refuse incompatible identities; preserve every unmanaged property/source."""
    payload = dry_run_loader(graph)
    existing_nodes = {}
    for n in snapshot["nodes"]:
        identifier = n["properties"].get("id")
        if identifier:
            existing_nodes.setdefault(identifier, []).append(n)
    existing_edges = {}
    by_element = {n["element_id"]: n["properties"].get("id") for n in snapshot["nodes"]}
    for e in snapshot["relationships"]:
        if e["properties"].get("id"):
            existing_edges.setdefault(e["properties"]["id"], []).append(e)
    plan = {"nodes": [], "edges": []}
    for row in payload["nodes"]:
        incoming = row["properties"]
        identifier = incoming["id"]
        matches = existing_nodes.get(identifier, [])
        if len(matches) > 1:
            raise ValueError("non_unique_existing_node_id")
        before = matches[0] if matches else None
        props = copy.deepcopy(incoming)
        if before:
            labels = set(before["labels"])
            kind = set(row["labels"]) & set(TYPES)
            if (
                labels & set(TYPES) != kind
                or not set(row["labels"]) <= labels
                or "MedResidentDemo" in labels
            ):
                raise ValueError("existing_node_label_contract_mismatch")
            prior = before["properties"]
            for key, value in incoming.items():
                if (
                    key
                    in {"id", "name", "text", "kind", "format", "answer", "explanation"}
                    and key in prior
                    and prior[key] != value
                ):
                    raise ValueError("existing_identity_or_statement_conflict")
            if "content" in prior:
                combined = merge_content(
                    json.loads(prior["content"]), json.loads(incoming["content"])
                )
                props["content"] = json.dumps(
                    combined, ensure_ascii=False, sort_keys=True
                )
            for key in ("aliases", "options"):
                if key in prior and key in incoming:
                    props[key] = merge_unique(prior[key], incoming[key])
            for key in NESTED - {"content"}:
                if key in prior and key in incoming:
                    props[key] = json.dumps(
                        merge_unique(json.loads(prior[key]), json.loads(incoming[key])),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
        action = (
            "create"
            if before is None
            else "skip"
            if all(before["properties"].get(k) == v for k, v in props.items())
            else "update"
        )
        plan["nodes"].append(
            {**row, "properties": props, "action": action, "before": before}
        )
    for row in payload["edges"]:
        identifier = row["properties"]["id"]
        matches = existing_edges.get(identifier, [])
        if len(matches) > 1:
            raise ValueError("non_unique_existing_edge_id")
        before = matches[0] if matches else None
        props = copy.deepcopy(row["properties"])
        if before:
            if (
                before["type"],
                by_element[before["start_node"]],
                by_element[before["end_node"]],
            ) != (row["type"], row["from_id"], row["to_id"]):
                raise ValueError("existing_edge_endpoints_or_type_conflict")
            if before["properties"].get("condition") != props.get("condition"):
                raise ValueError("existing_edge_condition_conflict")
            combined = merge_unique(
                json.loads(before["properties"]["sources"]),
                json.loads(props["sources"]),
            )
            props["sources"] = json.dumps(combined, ensure_ascii=False, sort_keys=True)
        action = (
            "create"
            if before is None
            else "skip"
            if all(before["properties"].get(k) == v for k, v in props.items())
            else "update"
        )
        plan["edges"].append(
            {**row, "properties": props, "action": action, "before": before}
        )
    hierarchy = [
        {
            "id": e["properties"].get("id", e["element_id"]),
            "from_id": by_element[e["start_node"]],
            "to_id": by_element[e["end_node"]],
            "type": e["type"],
        }
        for e in snapshot["relationships"]
        if e["type"] in {"IS_A", "HAS_SUBSKILL"}
    ]
    for edge in graph["edges"]:
        if edge["id"] in existing_edges:
            continue
        if cycle_if_added(hierarchy, edge):
            raise ValueError("cycle_with_existing_hierarchy")
        hierarchy.append(edge)
    plan["counts"] = {
        key: dict(Counter(r["action"] for r in plan[key])) for key in ("nodes", "edges")
    }
    return plan


def write_plan(tx, plan):
    """All labels/types come from dry_run_loader's closed schema, never model Cypher."""
    for row in plan["nodes"]:
        if row["action"] == "skip":
            continue
        labels = ":".join(row["labels"])
        if row["action"] == "create":
            tx.run(
                f"MERGE (n:{labels} {{id:$id}}) SET n += $props",
                id=row["properties"]["id"],
                props=row["properties"],
            ).consume()
        else:
            tx.run(
                "MATCH (n {id:$id}) SET n += $props",
                id=row["properties"]["id"],
                props=row["properties"],
            ).consume()
    for row in plan["edges"]:
        if row["action"] == "skip":
            continue
        tx.run(
            "MATCH (a {id:$left}), (b {id:$right}) "
            f"MERGE (a)-[r:{row['type']} {{id:$id}}]->(b) SET r += $props",
            left=row["from_id"],
            right=row["to_id"],
            id=row["properties"]["id"],
            props=row["properties"],
        ).consume()


def verify_result(before, after, plan):
    after_nodes = {n["properties"].get("id"): n for n in after["nodes"]}
    after_edges = {
        e["properties"].get("id"): e
        for e in after["relationships"]
        if e["properties"].get("id")
    }
    element_ids = {n["element_id"]: n["properties"].get("id") for n in after["nodes"]}
    target_nodes = {r["properties"]["id"] for r in plan["nodes"]}
    target_edges = {r["properties"]["id"] for r in plan["edges"]}
    for row in plan["nodes"]:
        found = after_nodes[row["properties"]["id"]]
        if not set(row["labels"]) <= set(found["labels"]) or any(
            found["properties"].get(k) != v for k, v in row["properties"].items()
        ):
            raise ValueError("node_readback_mismatch")
        for key in NESTED & row["properties"].keys():
            if json.loads(found["properties"][key]) != json.loads(
                row["properties"][key]
            ):
                raise ValueError("nested_readback_mismatch")
    for row in plan["edges"]:
        found = after_edges[row["properties"]["id"]]
        if (
            element_ids[found["start_node"]],
            found["type"],
            element_ids[found["end_node"]],
        ) != (row["from_id"], row["type"], row["to_id"]) or any(
            found["properties"].get(k) != v for k, v in row["properties"].items()
        ):
            raise ValueError("edge_readback_mismatch")
        if json.loads(found["properties"]["sources"]) != json.loads(
            row["properties"]["sources"]
        ):
            raise ValueError("edge_source_readback_mismatch")
    for key, identifiers in [("nodes", target_nodes), ("relationships", target_edges)]:
        old_by_element = {r["element_id"]: r for r in before[key]}
        new_by_element = {r["element_id"]: r for r in after[key]}
        for eid, row in old_by_element.items():
            if (
                row["properties"].get("id") not in identifiers
                and new_by_element.get(eid) != row
            ):
                raise ValueError("outside_scope_changed")
            if eid not in new_by_element:
                raise ValueError("existing_record_removed")
        creates = plan["counts"]["nodes" if key == "nodes" else "edges"].get(
            "create", 0
        )
        if len(after[key]) != len(before[key]) + creates:
            raise ValueError("unexpected_record_count_change")
    # New sources are additive even for nodes already present.
    for row in plan["nodes"]:
        if not row["before"]:
            continue
        old_props = row["before"]["properties"]
        found = after_nodes[row["properties"]["id"]]["properties"]
        for k, v in old_props.items():
            if k not in row["properties"] and found.get(k) != v:
                raise ValueError("unmanaged_property_changed")
        for c in json.loads(old_props.get("content", "[]")):
            if not any(
                n["text"] == c["text"] and all(s in n["sources"] for s in c["sources"])
                for n in json.loads(found["content"])
            ):
                raise ValueError("previous_content_or_sources_lost")
    return {
        "nodes_read_back": len(target_nodes),
        "edges_read_back": len(target_edges),
        "outside_scope_unchanged": True,
        "no_dangling_edges": True,
        "decoded_sources_match": True,
    }


def import_review(graph_file, audit_folder, *, env_file=DEFAULT_ENV_FILE, apply=False):
    from neo4j import GraphDatabase

    graph_file = Path(graph_file).resolve()
    folder = Path(audit_folder).resolve()
    if folder.exists():
        raise ValueError("import_audit_folder_must_be_new")
    graph = read_json(graph_file)
    dry_run_loader(graph)
    locators_checked = validate_locators(graph, graph_file.parent)
    values = dotenv_values(env_file, interpolate=False)
    keys = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"]
    missing = [k for k in keys if not values.get(k) or values[k].startswith("<")]
    if missing:
        raise ValueError("missing_" + "_".join(missing))
    uri = urlsplit(values["NEO4J_URI"])
    if uri.username or uri.password or uri.query or uri.fragment:
        raise ValueError("unsafe_neo4j_uri")
    folder.mkdir(parents=True)
    manifest = {
        "status": "preflight",
        "graph_sha256": fingerprint(graph),
        "uri": values["NEO4J_URI"],
        "database": values["NEO4J_DATABASE"],
        "env_file": str(Path(env_file).resolve()),
        "node_ids": [n["id"] for n in graph["nodes"]],
        "edge_ids": [e["id"] for e in graph["edges"]],
        "locators_checked": locators_checked,
        "expert_verified": False,
        "apply_requested": apply,
    }
    write_json(folder / "import-manifest.json", manifest)
    committed = False
    try:
        with GraphDatabase.driver(
            values["NEO4J_URI"],
            auth=(values["NEO4J_USERNAME"], values["NEO4J_PASSWORD"]),
            connection_timeout=5,
            connection_acquisition_timeout=10,
            max_transaction_retry_time=0,
        ) as driver:
            driver.verify_connectivity()
            with driver.session(database=values["NEO4J_DATABASE"]) as session:
                # One explicit transaction: no hidden driver transaction retries.
                with session.begin_transaction(timeout=120) as tx:
                    before = read_graph(tx, None)
                    plan = build_plan(graph, before)
                    write_json(folder / "before-all.json", before)
                    write_json(folder / "import-plan.json", plan)
                    manifest["counts"] = plan["counts"]
                    write_json(folder / "import-manifest.json", manifest)
                    if not apply:
                        manifest["status"] = "preflight_passed"
                    else:
                        write_plan(tx, plan)
                        # Verify within the transaction so failures roll back.
                        staged = read_graph(tx, None)
                        verify_result(before, staged, plan)
                        tx.commit()
                        committed = True
                if apply:
                    with session.begin_transaction(timeout=30) as tx:
                        after = read_graph(tx, None)
                    write_json(folder / "after-all.json", after)
                    manifest["verification"] = verify_result(before, after, plan)
                    manifest["status"] = "imported_and_verified"
    except Exception as exc:
        manifest.update(
            status="committed_verification_failed" if committed else "failed_no_commit",
            error_type=type(exc).__name__,
            error_code=getattr(exc, "code", None),
        )
        if isinstance(exc, ValueError):
            manifest["reason"] = (
                str(exc) if re_safe_reason(str(exc)) else "contract_validation_failed"
            )
        write_json(folder / "import-manifest.json", manifest)
        raise
    write_json(folder / "import-manifest.json", manifest)
    return manifest


def re_safe_reason(reason):
    return all(
        ch in "abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ" for ch in reason
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--audit-folder", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = import_review(
            args.graph, args.audit_folder, env_file=args.env_file, apply=args.apply
        )
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in ["status", "uri", "database", "counts", "locators_checked"]
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 -- driver errors may contain credentials
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_code": getattr(exc, "code", None),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
