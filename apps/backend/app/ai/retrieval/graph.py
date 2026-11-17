"""Bounded read-only KG lookup using the actual content.sources/edge.sources schema."""

import json
from dataclasses import dataclass, field

from neo4j import READ_ACCESS, AsyncGraphDatabase

RELATIONS = [
    "IS_A",
    "HAS_FINDING",
    "CLASSIFIED_BY",
    "HAS_CATEGORY",
    "EVALUATED_BY",
    "MANAGED_BY",
    "GUIDED_BY",
    "APPLIES_TO",
    "REQUIRES_KNOWLEDGE_OF",
]


def unpack(value):
    if isinstance(value, str):
        return json.loads(value)
    return value or []


@dataclass
class GraphCandidates:
    source: str
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    requests: int = 0
    error: str | None = None

    def references(self):
        refs = []
        for node in self.nodes:
            for block in unpack(node.get("content")):
                for source in block.get("sources", []):
                    refs.append(
                        {**source, "node_ids": [node["id"]], "edge_id": None, "condition": None}
                    )
            for source in unpack(node.get("sources")):
                refs.append(
                    {**source, "node_ids": [node["id"]], "edge_id": None, "condition": None}
                )
        for edge in self.edges:
            for source in unpack(edge.get("sources")):
                refs.append(
                    {
                        **source,
                        "node_ids": [edge["from_id"], edge["to_id"]],
                        "edge_id": edge.get("id"),
                        "condition": edge.get("condition"),
                    }
                )
        return refs


class Neo4jEvidenceRepository:
    def __init__(self, settings):
        self.settings = settings
        self.driver = None

    async def lookup(self, concept_ids):
        result = GraphCandidates("live_neo4j")
        ids = list(dict.fromkeys(concept_ids))[:3]
        if not ids:
            return result
        s = self.settings
        if not all((s.neo4j_uri, s.neo4j_username, s.neo4j_password)):
            result.error = "NEO4J_NOT_CONFIGURED"
            return result
        try:
            if self.driver is None:
                self.driver = AsyncGraphDatabase.driver(
                    s.neo4j_uri,
                    auth=(s.neo4j_username, s.neo4j_password),
                    connection_timeout=4,
                    connection_acquisition_timeout=4,
                    max_transaction_retry_time=0,
                )
            async with self.driver.session(
                database=s.neo4j_database, default_access_mode=READ_ACCESS
            ) as session:
                async with await session.begin_transaction(timeout=8) as tx:
                    result.requests += 1
                    records = await tx.run(
                        "MATCH (n) WHERE n.id IN $ids AND (n:MedicalConcept OR n:Skill) "
                        "RETURN properties(n) AS p LIMIT 3",
                        ids=ids,
                    )
                    result.nodes = [r["p"] for r in await records.data()]
                    if result.nodes:
                        result.requests += 1
                        records = await tx.run(
                            "MATCH (a)-[r]-(b) WHERE a.id IN $ids "
                            "AND type(r) IN $relations AND (b:MedicalConcept OR b:Skill) "
                            "RETURN a.id AS start,b.id AS end,properties(b) AS neighbor,"
                            "startNode(r).id AS rel_start,endNode(r).id AS rel_end,"
                            "type(r) AS kind,properties(r) AS p ORDER BY r.id LIMIT 24",
                            ids=[n["id"] for n in result.nodes],
                            relations=RELATIONS,
                        )
                        known = {n["id"] for n in result.nodes}
                        for row in await records.data():
                            if row["end"] not in known:
                                result.nodes.append(row["neighbor"])
                                known.add(row["end"])
                            result.edges.append(
                                {
                                    **row["p"],
                                    "from_id": row["rel_start"],
                                    "to_id": row["rel_end"],
                                    "type": row["kind"],
                                }
                            )
        except Exception as exc:
            # Driver text/URIs can contain credentials. Only a type is retained.
            result.error = "NEO4J_LOOKUP_FAILED:" + type(exc).__name__
            result.nodes = []
            result.edges = []
        return result

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None


class SnapshotEvidenceRepository:
    def __init__(self, path):
        from pathlib import Path

        from .semantic import sha256_file

        graph = json.loads(Path(path).read_text(encoding="utf-8"))
        self.snapshot_sha256 = sha256_file(path)
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.edges = graph["edges"]

    async def lookup(self, concept_ids):
        ids = list(dict.fromkeys(concept_ids))[:3]
        result = GraphCandidates(
            "offline_graph_snapshot", nodes=[self.nodes[n] for n in ids if n in self.nodes]
        )
        linked = [
            e
            for e in self.edges
            if e["type"] in RELATIONS and (e["from_id"] in ids or e["to_id"] in ids)
        ]
        result.edges = sorted(linked, key=lambda e: e["id"])[:24]
        present = {n["id"] for n in result.nodes}
        for e in result.edges:
            for n in (e["from_id"], e["to_id"]):
                if n not in present and n in self.nodes:
                    result.nodes.append(self.nodes[n])
                    present.add(n)
        return result

    async def close(self):
        pass
