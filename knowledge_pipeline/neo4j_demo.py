"""Import a technically validated sample as a scoped, review-gated Neo4j demo."""

import argparse
import json
from collections import Counter
from pathlib import Path

from dotenv import dotenv_values
from jsonschema import Draft202012Validator

from document_toolkit.common import fingerprint, read_json, write_json
from document_toolkit.config import DEFAULT_ENV_FILE

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRIAL = ROOT / "data/knowledge-extraction/trial-20261028-graduate"
LABELS = {"DemoDataset", "DocumentEdition", "ExtractionRun", "OCRArtifact",
          "SourceUnit", "EvidenceExcerpt", "MedicalConceptCandidate", "MedicalStatement"}
RELATIONS = {"HAS_DOCUMENT", "HAS_RUN", "HAS_OCR_ARTIFACT", "HAS_SOURCE_UNIT",
             "HAS_STATEMENT", "HAS_EXCERPT", "MENTIONS", "ABOUT", "SUPPORTED_BY", "GENERATED"}


def build_graph(trial):
    trial = Path(trial).resolve()
    if not trial.is_relative_to(ROOT / "data/knowledge-extraction"):
        raise ValueError("Use a trial inside data/knowledge-extraction")
    collections = {}
    validator = Draft202012Validator(read_json(ROOT / "knowledge_pipeline/schemas/records.schema.json"))
    for name in ("source_units", "concept_candidates", "medical_statements"):
        collections[name] = [json.loads(line) for line in
            (trial / "runs/validated" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
        for record in collections[name]:
            validator.validate(record)
            if (record["expert_review"] != "unverified" or record["usable_as_default_evidence"]
                    or record["validation"]["json_schema"] != "passed"
                    or record["validation"]["quote_locator"] != "passed"):
                raise ValueError("Demo requires technically validated, explicitly unreviewed records")
    digest = fingerprint(collections)
    demo_id = "graduate-20261028-" + digest[:12]
    nodes, edges = {}, {}

    def node(label, identifier, display_name, **properties):
        if identifier in nodes:
            raise ValueError("Duplicate demo node ID")
        if label not in LABELS:
            raise ValueError("Unexpected node label")
        clean = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict)
                 or isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v)
                 else v for k, v in properties.items()}
        nodes[identifier] = {"id": identifier, "label": label, "properties": {
            **clean, "display_name": display_name, "name": display_name, "is_demo": True,
            "expert_review": "unverified", "usable_as_default_evidence": False,
        }}

    def edge(start, relation, end):
        if relation not in RELATIONS:
            raise ValueError("Unexpected relation")
        edges[(start, relation, end)] = {"start": start, "type": relation, "end": end}

    node("DemoDataset", demo_id, "Demo OCR graduate · Chưa duyệt", fingerprint=digest,
         input_trial=trial.relative_to(ROOT).as_posix(), description="Presentation demo; not a clinical KG")
    books = {b["document_edition_id"]: b for b in read_json(trial / "inventory.json")["documents"]}
    artifacts = {a["source_pdf_sha256"]: a for a in read_json(trial / "ocr-input-manifest.json")}
    all_records = sum(collections.values(), [])
    for edition in sorted({r["document_edition_id"] for r in all_records}):
        book = books[edition]
        node("DocumentEdition", edition, f"{book['title']} ({book['publication_year']})",
             title=book["title"], publication_year=book["publication_year"],
             source_sha256=book["source_sha256"], source_id=book["source_id"])
        edge(demo_id, "HAS_DOCUMENT", edition)
        artifact = artifacts[book["source_sha256"]]
        aid = "OCR_" + artifact["sha256"][:24]
        node("OCRArtifact", aid, "OCR sẵn · " + str(artifact["model"]),
             artifact_sha256=artifact["sha256"], artifact_path=artifact["path"],
             model=artifact["model"], new_ocr_calls=0)
        edge(edition, "HAS_OCR_ARTIFACT", aid)
    for run in sorted({r["extraction_run_id"] for r in all_records}):
        first = next(r for r in all_records if r["extraction_run_id"] == run)
        node("ExtractionRun", run, "LLM extraction · Chưa duyệt", model=first["model"],
             schema_prompt_code_fingerprint=first["schema_prompt_code_fingerprint"])
        edge(demo_id, "HAS_RUN", run)
    for unit in collections["source_units"]:
        uid = unit["source_unit_id"]
        node("SourceUnit", uid, unit["title"], title=unit["title"],
             document_edition_id=unit["document_edition_id"], validation=unit["validation"],
             source_sha256=unit["source_sha256"])
        edge(unit["document_edition_id"], "HAS_SOURCE_UNIT", uid)
        edge(unit["extraction_run_id"], "GENERATED", uid)
        for support in unit["supports"]:
            eid = "EXCERPT_" + fingerprint([uid, support])[:24]
            node("EvidenceExcerpt", eid, f"PDF {support['pdf_page']} · trang in {support['printed_page_label']}",
                 **support)
            edge(uid, "HAS_EXCERPT", eid)
    for concept in collections["concept_candidates"]:
        cid = concept["concept_candidate_id"]
        node("MedicalConceptCandidate", cid, concept["verbatim_name"],
             verbatim_name=concept["verbatim_name"], proposed_name=concept["proposed_name"],
             concept_type=concept["concept_type"], aliases=concept["aliases"],
             canonical_concept_id=None, semantic_support="needs_review")
        edge(concept["extraction_run_id"], "GENERATED", cid)
        for uid in concept["source_unit_ids"]:
            edge(uid, "MENTIONS", cid)
    for statement in collections["medical_statements"]:
        sid = statement["statement_id"]
        props = {k: v for k, v in statement.items()
                 if k not in ("statement_id", "source_unit_ids", "concept_ids")}
        node("MedicalStatement", sid, statement["statement_type"] + " · " + statement["text"][:70],
             **props)
        edge(statement["document_edition_id"], "HAS_STATEMENT", sid)
        edge(statement["extraction_run_id"], "GENERATED", sid)
        for uid in statement["source_unit_ids"]:
            edge(sid, "SUPPORTED_BY", uid)
        for cid in statement["concept_ids"]:
            edge(sid, "ABOUT", cid)
    if any(e["start"] not in nodes or e["end"] not in nodes for e in edges.values()):
        raise ValueError("Dangling graph reference; no import applied")
    return {"demo_id": demo_id, "fingerprint": digest, "nodes": list(nodes.values()),
            "edges": list(edges.values())}


def import_graph(graph, config):
    from neo4j import GraphDatabase

    keys = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
    if any(not config.get(k) or config[k].startswith("<") for k in keys):
        raise ValueError("Fill NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE in root .env")

    def write(tx):
        existing = tx.run(
            "MATCH (n:MedResidentDemo {demo_id:$demo_id, id:$demo_id}) RETURN n.fingerprint AS f",
            demo_id=graph["demo_id"]).single()
        if existing and existing["f"] != graph["fingerprint"]:
            raise ValueError("Existing demo fingerprint differs; no changes applied")
        for label in sorted(LABELS):
            batch = [n for n in graph["nodes"] if n["label"] == label]
            if batch:
                tx.run("UNWIND $rows AS row MERGE (n:MedResidentDemo {demo_id:$demo_id,id:row.id}) "
                             f"SET n:{label} SET n += row.properties",
                       rows=batch, demo_id=graph["demo_id"]).consume()
        for relation in sorted(RELATIONS):
            batch = [e for e in graph["edges"] if e["type"] == relation]
            if batch:
                tx.run("UNWIND $rows AS row "
                    "MATCH (a:MedResidentDemo {demo_id:$demo_id,id:row.start}) "
                    "MATCH (b:MedResidentDemo {demo_id:$demo_id,id:row.end}) "
                    f"MERGE (a)-[r:{relation} {{demo_id:$demo_id}}]->(b) "
                    "SET r.is_demo=true, r.semantic_support='needs_review'",
                    rows=batch, demo_id=graph["demo_id"]).consume()
        count = tx.run("MATCH (n:MedResidentDemo {demo_id:$demo_id}) RETURN count(n) AS count",
                             demo_id=graph["demo_id"]).single()["count"]
        relationships = tx.run("MATCH (:MedResidentDemo {demo_id:$demo_id})"
            "-[r {demo_id:$demo_id}]->(:MedResidentDemo {demo_id:$demo_id}) RETURN count(r) AS count",
            demo_id=graph["demo_id"]).single()["count"]
        if count != len(graph["nodes"]) or relationships != len(graph["edges"]):
            raise ValueError("Graph counts differ; transaction rolled back")
        return {"nodes": count, "relationships": relationships}

    with GraphDatabase.driver(config["NEO4J_URI"],
            auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
            connection_timeout=5, connection_acquisition_timeout=10,
            max_transaction_retry_time=0) as driver:
        driver.verify_connectivity()
        with driver.session(database=config["NEO4J_DATABASE"]) as session:
            with session.begin_transaction(timeout=30) as tx:
                result = write(tx)
                tx.commit()
                return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, default=DEFAULT_TRIAL)
    parser.add_argument("--apply", action="store_true", help="Write this demo to configured Neo4j")
    args = parser.parse_args()
    try:
        graph = build_graph(args.trial)
        folder = args.trial / "neo4j-demo"
        write_json(folder / "graph-payload.json", graph)
        query = (f"MATCH p=(a:MedResidentDemo {{demo_id:'{graph['demo_id']}'}})"
                 f"-[r]->(b:MedResidentDemo {{demo_id:'{graph['demo_id']}'}}) RETURN p LIMIT 100;\n")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "view.cypher").write_text(query, encoding="utf-8")
        summary = {"demo_id": graph["demo_id"], "status": "prepared",
                   "nodes": len(graph["nodes"]), "relationships": len(graph["edges"]),
                   "labels": dict(Counter(n["label"] for n in graph["nodes"])),
                   "expert_review": "unverified", "default_evidence_count": 0}
        if args.apply:
            config = dotenv_values(DEFAULT_ENV_FILE, interpolate=False, encoding="utf-8-sig")
            summary.update(import_graph(graph, config), status="imported")
        write_json(folder / "import-report.json", summary)
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        # Driver errors can contain credentials: only disclose type and server error code.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "error_code": getattr(exc, "code", None)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
