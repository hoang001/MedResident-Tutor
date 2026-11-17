import asyncio
import hashlib
import json
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from neo4j import READ_ACCESS, AsyncGraphDatabase

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.modules.knowledge.study_scope import resident_study_scope

PROGRAM = "HMU_RESIDENCY_SURGERY_ORTHOPEDICS_2025"
CLINICAL_TYPES = {
    "Condition",
    "Anatomy",
    "Finding",
    "Classification",
    "ClassificationCategory",
    "DiagnosticMethod",
    "Intervention",
    "Drug",
    "ClinicalPrinciple",
    "Skill",
    "SampleQuestion",
}
TREE_TYPES = {"Curriculum", "CurriculumGroup", "Course", "CurriculumRequirement"}
CURRICULUM_TYPES = TREE_TYPES | {
    "CurriculumOutcome",
    "CurriculumObjective",
    "CurriculumSource",
    "CurriculumCareerPath",
    "CurriculumStudyPath",
    "CurriculumReference",
}
PUBLIC_FIELDS = {
    "course_code",
    "course_name",
    "year",
    "round",
    "total_credits",
    "theory_credits",
    "practice_credits",
    "content_status",
    "group_id",
    "display_order",
    "requirement",
    "description",
    "text",
    "outcome_code",
    "competency_domain",
    "scope",
    "publisher",
    "snapshot_sha256",
    "fetched_at_utc",
    "review_status",
    "current_program_confirmed",
    "hmu_lesson_access",
    "hmu_listing_status",
    "selection_rule",
    "choose_count",
    "offered_count",
    "required_credits",
    "required_level",
    "level",
    "requirement_type",
    "credit_status",
    "status",
}


def unpack(value, default):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value if value is not None else default


def folded(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
        if not unicodedata.combining(c)
    )


def web_url(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if url.scheme == "https" and (host == "hmu.edu.vn" or host.endswith(".hmu.edu.vn")):
            if not url.username and not url.password:
                return value
    except ValueError:
        pass
    return None


def citation(value, books: dict) -> dict | None:
    if not isinstance(value, dict) or value.get("source_id") not in books:
        return None
    book = books[value["source_id"]]
    pages = value.get("pdf_pages", [])
    return {
        "source_id": book["id"],
        "title": book["title"],
        "pdf_pages": sorted({p for p in pages if type(p) is int and 1 <= p <= book["pages"]}),
        "printed_pages": value.get("printed_pages", []),
        "excerpt": str(value.get("excerpt", "")),
    }


class Snapshot:
    def __init__(self, raw_nodes: list, raw_edges: list, catalog: dict, coverage: dict):
        self.books = {b["id"]: b for b in catalog["books"]}
        self.coverage = coverage
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.search_text: dict[str, str] = {}
        for row in raw_nodes:
            props, labels = row["p"], set(row["labels"])
            node_type = next((t for t in sorted(labels) if t in CLINICAL_TYPES), None)
            curricular = props.get("curriculum_id") == PROGRAM and bool(labels & CURRICULUM_TYPES)
            if curricular:
                node_type = next(t for t in sorted(labels) if t in CURRICULUM_TYPES)
            if not node_type or not isinstance(props.get("id"), str):
                continue
            blocks = []
            citations = []
            for block in unpack(props.get("content"), []):
                if not isinstance(block, dict):
                    continue
                refs = [c for s in block.get("sources", []) if (c := citation(s, self.books))]
                if refs:
                    blocks.append({"text": str(block.get("text", "")), "sources": refs})
                    citations.extend(refs)
            citations.extend(
                c for s in unpack(props.get("sources"), []) if (c := citation(s, self.books))
            )
            if not curricular and not citations:
                continue
            title = str(props.get("name") or props.get("text") or props["id"])
            unique = {json.dumps(c, sort_keys=True, ensure_ascii=False): c for c in citations}
            citations = list(unique.values())
            book_ids = sorted({c["source_id"] for c in citations})
            chapters = []
            for book_id in book_ids:
                pages = {p for c in citations if c["source_id"] == book_id for p in c["pdf_pages"]}
                for chapter in self.books[book_id]["chapters"]:
                    if any(chapter["start"] <= p <= chapter["end"] for p in pages):
                        chapters.append({"source_id": book_id, "number": chapter["number"]})
            metadata = {k: props[k] for k in PUBLIC_FIELDS if k in props}
            for key in ("url", "hmu_course_url"):
                if url := web_url(props.get(key)):
                    metadata[key] = url
            evidence = []
            for key in ("evidence_json", "hmu_listing_evidence_json"):
                entries = unpack(props.get(key), [])
                if isinstance(entries, dict):
                    entries = [entries]
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    # Evidence stays at its source scope, with no server filesystem paths.
                    evidence.append(
                        {
                            k: e[k]
                            for k in ("source_id", "quote", "locator", "snapshot_sha256")
                            if k in e
                        }
                        | ({"url": url} if (url := web_url(e.get("url"))) else {})
                    )
            payload = {
                "id": props["id"],
                "type": node_type,
                "title": title,
                "curricular": curricular,
                "content": blocks,
                "sources": citations,
                "book_ids": book_ids,
                "chapters": chapters,
                "metadata": metadata,
                "evidence": evidence,
                "review_status": "source_reviewed_draft"
                if not curricular
                else props.get("review_status", "awaiting_teacher_content"),
                "expert_verified": False,
            }
            self.nodes[props["id"]] = payload
            self.search_text[props["id"]] = folded(
                title + " " + " ".join(b["text"] for b in blocks)
            )
        for edge in raw_edges:
            if edge["start"] not in self.nodes or edge["end"] not in self.nodes:
                continue
            p = edge.get("p", {})
            self.edges.append(
                {
                    "start": edge["start"],
                    "end": edge["end"],
                    "type": edge["type"],
                    "condition": p.get("condition", ""),
                    "sources": [
                        c for s in unpack(p.get("sources"), []) if (c := citation(s, self.books))
                    ],
                }
            )
        incident = {node_id: [] for node_id in self.nodes}
        for edge in self.edges:
            incident[edge["start"]].append(edge)
            if edge["start"] != edge["end"]:
                incident[edge["end"]].append(edge)
        for node_id, node in self.nodes.items():
            related = sorted(
                incident[node_id], key=lambda e: json.dumps(e, sort_keys=True, ensure_ascii=False)
            )
            node["revision"] = hashlib.sha256(
                json.dumps([node, related], sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()

    def get(self, node_id: str) -> dict:
        if node_id not in self.nodes:
            raise NotFoundError("KNOWLEDGE_NOT_FOUND", "Knowledge item not found")
        return self.nodes[node_id]

    @staticmethod
    def brief(node: dict) -> dict:
        return {
            k: node[k]
            for k in ("id", "title", "type", "book_ids", "chapters", "revision", "review_status")
        } | {"snippet": (node["content"][0]["text"] if node["content"] else node["title"])[:240]}

    def detail(self, node_id: str) -> dict:
        node = self.get(node_id)
        edges = [e for e in self.edges if node_id in (e["start"], e["end"])]
        return node | {
            "relations": [
                e
                | {
                    "target": self.brief(
                        self.nodes[e["end"] if e["start"] == node_id else e["start"]]
                    ),
                    "outgoing": e["start"] == node_id,
                }
                for e in edges[:60]
            ],
            "relation_count": len(edges),
        }

    def search(self, q="", book="", chapter=None, kind="", offset=0, limit=20):
        if book and book not in self.books:
            raise NotFoundError("SOURCE_NOT_FOUND", "Source not found")
        terms = folded(q).split()
        items = []
        for node in self.nodes.values():
            if node["curricular"] or (book and book not in node["book_ids"]):
                continue
            if kind and node["type"] != kind:
                continue
            if chapter is not None and not any(
                c["number"] == chapter and (not book or c["source_id"] == book)
                for c in node["chapters"]
            ):
                continue
            haystack = self.search_text[node["id"]]
            if not all(t in haystack for t in terms):
                continue
            score = sum(10 for t in terms if t in folded(node["title"]))
            items.append((score, node))
        items.sort(key=lambda item: (-item[0], folded(item[1]["title"]), item[1]["id"]))
        return {
            "total": len(items),
            "offset": offset,
            "limit": limit,
            "items": [self.brief(n) for _, n in items[offset : offset + limit]],
        }

    def curriculum(self):
        scope = resident_study_scope()
        focus_codes = {c["course_code"] for group in scope["groups"] for c in group["courses"]}
        nodes = [n for n in self.nodes.values() if n["curricular"]]
        courses = []
        for node in nodes:
            if node["type"] != "Course":
                continue
            focused = node["metadata"].get("course_code") in focus_codes
            mapping = next(
                (
                    c
                    for c in self.coverage.get("courses", [])
                    if c["course_id"] == node["metadata"].get("course_code")
                ),
                {},
            )
            courses.append(
                node
                | {
                    "study_role": "focus" if focused else "prior_outcomes_only",
                    "course_outcomes_status": "awaiting_teacher_confirmation",
                    "suggested_topics": [
                        {
                            "title": t["topic_name"],
                            "status": "provisional",
                            "source_ids": [s for s in t.get("source_links", []) if s in self.books],
                        }
                        for t in mapping.get("topics", [])
                        if focused
                    ],
                }
            )
        return {
            "nodes": [n for n in nodes if n["type"] != "Course"] + courses,
            "edges": [
                e
                for e in self.edges
                if self.nodes[e["start"]]["curricular"] and self.nodes[e["end"]]["curricular"]
            ],
            "current_program_confirmed": False,
            "study_scope": scope,
        }

    def sources(self, root: Path):
        return [
            {k: v for k, v in b.items() if k != "filename"}
            | {
                "pdf_available": (root / "raw-source" / b["filename"]).is_file(),
                "node_count": sum(b["id"] in n["book_ids"] for n in self.nodes.values()),
            }
            for b in self.books.values()
        ]

    def pdf_path(self, source_id: str, root: Path) -> Path:
        book = self.books.get(source_id)
        if not book:
            raise NotFoundError("SOURCE_NOT_FOUND", "Source not found")
        base = (root / "raw-source").resolve()
        path = (base / book["filename"]).resolve()
        if not path.is_relative_to(base) or path.suffix.lower() != ".pdf" or not path.is_file():
            raise NotFoundError("SOURCE_FILE_NOT_FOUND", "Source PDF is not available")
        return path


class GraphStore:
    def __init__(self):
        self.driver = None
        self.cached: Snapshot | None = None
        self.expires = 0.0
        self.lock = asyncio.Lock()

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None
        self.cached = None

    async def snapshot(self) -> Snapshot:
        settings = get_settings()
        if self.cached and time.monotonic() < self.expires:
            return self.cached
        async with self.lock:
            if self.cached and time.monotonic() < self.expires:
                return self.cached
            if not all((settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)):
                raise AppError("KNOWLEDGE_UNAVAILABLE", "Neo4j is not configured", 503)
            try:
                root = settings.knowledge_data_root
                catalog = json.loads((root / "library/catalog.json").read_text(encoding="utf-8"))
                coverage = json.loads(
                    (root / "coverage/course_topic_source_map.json").read_text(encoding="utf-8")
                )
                if not self.driver:
                    self.driver = AsyncGraphDatabase.driver(
                        settings.neo4j_uri,
                        auth=(settings.neo4j_username, settings.neo4j_password),
                        connection_timeout=5,
                        connection_acquisition_timeout=5,
                        max_transaction_retry_time=0,
                    )
                async with (
                    self.driver.session(
                        database=settings.neo4j_database, default_access_mode=READ_ACCESS
                    ) as session,
                    await session.begin_transaction(timeout=20) as tx,
                ):
                    result = await tx.run(
                        "MATCH (n) WHERE (n:CurriculumEntity AND n.curriculum_id=$program) "
                        "OR n:MedicalConcept OR n:Skill OR n:SampleQuestion "
                        "RETURN labels(n) AS labels, properties(n) AS p LIMIT 20001",
                        program=PROGRAM,
                    )
                    nodes = await result.data()
                    result = await tx.run(
                        "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids "
                        "RETURN a.id AS start,b.id AS end,type(r) AS type,properties(r) AS p "
                        "LIMIT 50001",
                        ids=[n["p"]["id"] for n in nodes if "id" in n["p"]],
                    )
                    edges = await result.data()
                if len(nodes) > 20000 or len(edges) > 50000:
                    raise ValueError("Knowledge snapshot exceeds configured capacity")
                self.cached = Snapshot(nodes, edges, catalog, coverage)
                self.expires = time.monotonic() + settings.knowledge_cache_seconds
                return self.cached
            except Exception as exc:
                # Driver errors can include connection details: do not log/return their text.
                raise AppError(
                    "KNOWLEDGE_UNAVAILABLE", "Knowledge library is unavailable", 503
                ) from exc


@lru_cache
def get_graph_store() -> GraphStore:
    return GraphStore()
