"""Read Neo4j nodes/relationships into a portable JSON file; never writes to Neo4j."""

import argparse
import base64
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from document_toolkit.common import write_json
from document_toolkit.config import DEFAULT_ENV_FILE

DEFAULT_DEMO_ID = "graduate-20261028-0381f7dd8a7e"
DEFAULT_OUTPUT = DEFAULT_ENV_FILE.parent / "data/exports/neo4j-demo.json"


def json_value(value):
    """Keep Neo4j temporal/spatial/binary properties JSON-safe without losing their type."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"$type": "float", "value": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"$type": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if hasattr(value, "srid"):
        return {"$type": "point", "srid": value.srid, "coordinates": list(value)}
    if hasattr(value, "iso_format") or hasattr(value, "isoformat"):
        formatter = getattr(value, "iso_format", None) or value.isoformat
        return {"$type": type(value).__name__, "value": formatter()}
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    raise TypeError("Unsupported property type: " + type(value).__name__)


def read_graph(tx, demo_id):
    nodes = []
    for row in tx.run(
        "MATCH (n) WHERE $demo_id IS NULL OR (n:MedResidentDemo AND n.demo_id=$demo_id) "
        "RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS properties "
        "ORDER BY element_id", demo_id=demo_id,
    ):
        nodes.append({"element_id": row["element_id"], "labels": sorted(row["labels"]),
                      "properties": json_value(row["properties"])})
    relationships = []
    for row in tx.run(
        "MATCH (a)-[r]->(b) WHERE $demo_id IS NULL OR "
        "(a:MedResidentDemo AND b:MedResidentDemo AND a.demo_id=$demo_id AND b.demo_id=$demo_id) "
        "RETURN elementId(r) AS element_id, type(r) AS type, elementId(a) AS start, "
        "elementId(b) AS end, properties(r) AS properties ORDER BY element_id", demo_id=demo_id,
    ):
        relationships.append({"element_id": row["element_id"], "type": row["type"],
                              "start_node": row["start"], "end_node": row["end"],
                              "properties": json_value(row["properties"])})
    node_ids = {node["element_id"] for node in nodes}
    if any(r["start_node"] not in node_ids or r["end_node"] not in node_ids for r in relationships):
        raise ValueError("Graph changed during export; retry to obtain complete references")
    return {"nodes": nodes, "relationships": relationships}


def export_neo4j_json(output_path=DEFAULT_OUTPUT, *, env_file=DEFAULT_ENV_FILE,
                      demo_id=DEFAULT_DEMO_ID, overwrite=False):
    """Export a demo, or the configured database when demo_id=None. Returns a safe summary."""
    from neo4j import GraphDatabase, READ_ACCESS

    output = Path(output_path).resolve()
    if output.suffix.lower() != ".json" or output == Path(env_file).resolve():
        raise ValueError("Choose a JSON output file distinct from configuration")
    if output.exists() and not overwrite:
        raise FileExistsError("Output already exists; use overwrite=True or --overwrite")
    config = dotenv_values(env_file, interpolate=False, encoding="utf-8-sig")
    keys = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
    if any(not config.get(key) or config[key].startswith("<") for key in keys):
        raise ValueError("Fill the four NEO4J_* settings in root .env")
    with GraphDatabase.driver(config["NEO4J_URI"],
            auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
            connection_timeout=5, connection_acquisition_timeout=10,
            max_transaction_retry_time=0) as driver:
        driver.verify_connectivity()
        with driver.session(database=config["NEO4J_DATABASE"], default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=60) as tx:
                graph = read_graph(tx, demo_id)
                tx.commit()
    summary = {"nodes": len(graph["nodes"]), "relationships": len(graph["relationships"]),
               "labels": dict(Counter(label for n in graph["nodes"] for label in n["labels"])),
               "relationship_types": dict(Counter(r["type"] for r in graph["relationships"]))}
    document = {"format": "medresident-neo4j-export-v1",
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "scope": {"database": config["NEO4J_DATABASE"], "demo_id": demo_id,
                          "all_nodes": demo_id is None}, "summary": summary, **graph}
    # Do not serialize the connection config, URI, password, or authentication headers.
    write_json(output, document)
    return {"output_file": str(output), **summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--demo-id", default=DEFAULT_DEMO_ID)
    scope.add_argument("--all", action="store_true", help="Export all nodes in the configured database")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(export_neo4j_json(args.output, env_file=args.env_file,
            demo_id=None if args.all else args.demo_id, overwrite=args.overwrite), ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "error_code": getattr(exc, "code", None)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
