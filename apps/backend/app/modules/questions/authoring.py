"""Admin-only source-grounded authoring, separate from the locked grading contract."""

import asyncio
import copy
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.ai.authoring_contract import SYSTEM, VERSION, Proposal, Scope
from app.ai.retrieval.books import PracticeBookRetriever
from app.ai.retrieval.evidence import content_hash, digest
from app.ai.retrieval.factory import book_index
from app.ai.retrieval.graph import Neo4jEvidenceRepository
from app.core.config import get_settings
from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit


class Selection(BaseModel):
    bundle_token: str = Field(max_length=100000)
    selected_ids: list[str] = Field(min_length=1, max_length=3)


class ProposalRequest(Selection):
    scope: Scope


def seal(value, kind):
    return jwt.encode(
        {"kind": kind, "value": value, "exp": datetime.now(UTC) + timedelta(hours=2)},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )


def unseal(token, kind):
    try:
        data = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        if data["kind"] != kind:
            raise ValueError()
        return data["value"]
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(
            422, "Authoring evidence/proposal expired or invalid; retrieve again"
        ) from None


def selected(body):
    bundle = unseal(body.bundle_token, "evidence")
    chosen = set(body.selected_ids)
    evidence = [e for e in bundle["evidence"] if e["source_unit_id"] in chosen]
    if len(chosen) != len(evidence) or len(chosen) != len(body.selected_ids):
        raise HTTPException(422, "Unknown or duplicate evidence IDs")
    return bundle, evidence


async def retrieve(scope, settings=None):
    settings = settings or get_settings()
    index = await asyncio.to_thread(
        book_index,
        str(settings.practice_retrieval_corpus),
        str(settings.practice_retrieval_encoder),
    )
    # Exact title/alias phrase matching is inspectable; course is only an organization label.
    graph = Neo4jEvidenceRepository(settings)
    ids, discovery_error = [], None
    discovery_queries = 0
    if all((settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)):
        from neo4j import READ_ACCESS, AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            connection_timeout=4,
            max_transaction_retry_time=0,
        )
        try:
            async with driver.session(
                database=settings.neo4j_database, default_access_mode=READ_ACCESS
            ) as session:
                async with await session.begin_transaction(timeout=8) as tx:
                    discovery_queries += 1
                    rows = await tx.run(
                        "MATCH (n) WHERE (n:MedicalConcept OR n:Skill) AND "
                        "any(term IN [coalesce(n.name,''),coalesce(n.title,'')] + "
                        "coalesce(n.aliases,[]) WHERE size(term)>=4 AND "
                        "toLower($q) CONTAINS toLower(term)) "
                        "RETURN n.id AS id ORDER BY size(coalesce(n.name,n.title,'')) DESC LIMIT 3",
                        q=scope.topic + " " + scope.question,
                    )
                    ids = [r["id"] for r in await rows.data()]
        except Exception as exc:
            discovery_error = "KG_DISCOVERY_UNAVAILABLE:" + type(exc).__name__
        finally:
            await driver.close()
    allowed = sorted({c["source_id"] for c in index.corpus})
    sources = scope.source_ids or allowed
    if not set(sources) <= set(allowed):
        raise HTTPException(422, "Unknown source scope")
    dynamic_mapping = {
        "version": VERSION,
        "questions": {
            "authoring": {
                "question_sha256": content_hash(scope.question),
                "concept_ids": ids,
                "source_ids": sources,
            }
        },
    }
    retriever = PracticeBookRetriever(
        index,
        graph,
        dynamic_mapping,
        strategy="hybrid",
        min_similarity=settings.practice_retrieval_min_similarity,
    )
    try:
        bundle = await retriever.retrieve("authoring", scope.question, str(uuid.uuid4()))
    finally:
        await graph.close()
    bundle.trace["concept_discovery"] = "title_alias_phrase_match"
    bundle.trace["concept_discovery_queries"] = discovery_queries
    bundle.trace["neo4j_queries"] += discovery_queries
    bundle.trace["discovery_error"] = discovery_error
    if not ids:
        bundle.trace["fallback_reason"] = discovery_error or "no_title_alias_match_vector_fallback"
    value = {
        "scope": scope.model_dump(),
        "evidence": bundle.evidence,
        "provenance": bundle.provenance,
        "trace": bundle.trace,
    }
    from pathlib import Path

    catalog = json.loads(
        (Path(settings.practice_retrieval_corpus) / "catalog.json").read_text(encoding="utf-8")
    )
    books = {b["id"]: b for b in catalog["books"]}
    for p in value["provenance"]:
        p["book_title"] = books[p["source_id"]]["title"]
        p["book_filename"] = books[p["source_id"]]["filename"]
    return {
        **value,
        "bundle_token": seal(value, "evidence"),
        "status": "candidates_need_review" if bundle.evidence else "no_evidence",
    }


async def materialize(session, admin_id, body):
    bundle, evidence = selected(body)
    if bundle.get("trace", {}).get("corpus_sha256"):
        from pathlib import Path

        manifest = json.loads(
            (Path(get_settings().practice_retrieval_corpus) / "index-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        if manifest["corpus_sha256"] != bundle["trace"]["corpus_sha256"]:
            raise HTTPException(409, "Source corpus version changed; retrieve again")
    result = []
    for e in evidence:
        p = next(p for p in bundle["provenance"] if p["source_unit_id"] == e["source_unit_id"])
        identity = digest({"evidence": e, "provenance": p})
        sid = "AUTH_SU_" + identity
        # Serialize concurrent synchronization without mutating existing source units.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": sid}
        )
        unit = await session.scalar(select(SourceUnit).where(SourceUnit.external_id == sid))
        if unit is None:
            did = "AUTH_DOC_" + digest([e["source_id"], p["sha256"]])
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": did}
            )
            doc = await session.scalar(select(Document).where(Document.external_id == did))
            if doc is None:
                doc = Document(
                    external_id=did,
                    name=p.get("book_title", e["source_id"]),
                    original_filename=e["source_id"] + ".pdf",
                    storage_path="authoring/" + did,
                    mime_type="application/pdf",
                    file_size=0,
                    created_by=admin_id,
                    source_sha256=p["sha256"],
                    version=str(p.get("book_year") or "unknown"),
                    import_metadata={
                        "original_source_id": e["source_id"],
                        "provenance": p,
                        "catalog": {
                            "title": p.get("book_title", e["source_id"]),
                            "year": p.get("book_year"),
                        },
                    },
                )
                session.add(doc)
                await session.flush()
            unit = SourceUnit(
                external_id=sid,
                document_id=doc.id,
                title=e["title"],
                content=e["content"],
                pdf_page_start=e["page_start"],
                pdf_page_end=e["page_end"],
                import_metadata={
                    "expert_review": {"status": "unverified"},
                    "authoring_provenance": p,
                    "content_sha256": content_hash(e["content"]),
                },
            )
            session.add(unit)
            await session.flush()
        result.append({**e, "source_unit_id": sid, "retrieval_id": e["source_unit_id"]})
    return result


def validate_proposal(value, evidence, max_score):
    import math

    proposal = Proposal.model_validate(value)
    known = {e["source_unit_id"] for e in evidence}
    if any(not set(c.source_unit_ids) <= known for c in proposal.criteria):
        raise HTTPException(422, "Proposal contains unknown evidence IDs")
    if not math.isclose(sum(c.max_score for c in proposal.criteria), max_score, abs_tol=1e-9):
        raise HTTPException(422, "Proposal score total mismatch")
    return proposal.model_dump()


async def propose(body):
    bundle, evidence = selected(body)
    if bundle["scope"] != body.scope.model_dump():
        raise HTTPException(409, "Question or scope changed; retrieve again")
    settings = get_settings()
    if settings.authoring_provider == "off":
        from app.core.exceptions import AppError

        raise AppError(
            "AUTHORING_MODEL_OFF", "Authoring model is off; manual drafting remains available", 503
        )
    if (
        settings.authoring_provider in {"openai", "service_http", "runpod"}
        and not settings.model_calls_enabled
    ):
        from app.core.exceptions import AppError

        raise AppError("MODEL_CALLS_DISABLED", "Remote model calls are disabled", 503)
    if settings.authoring_provider == "runpod":
        from app.ai.model_service import ModelServiceClient, ModelServiceError
        from app.core.exceptions import AppError

        try:
            result = await ModelServiceClient(settings).authoring_propose(
                {
                    "version": VERSION,
                    "system": SYSTEM,
                    "scope": body.scope.model_dump(),
                    "evidence": evidence,
                }
            )
        except ModelServiceError as exc:
            raise AppError(exc.code, "Authoring model request failed", exc.status) from None
        value = validate_proposal(result["proposal"], evidence, body.scope.max_score)
        provenance = {
            "version": VERSION,
            "mode": "runpod_base_model",
            "scope": body.scope.model_dump(),
            "selected_ids": body.selected_ids,
            "proposal": value,
            "model_metadata": result.get("model_metadata", {}),
            "timing": result.get("timing", {}),
        }
        return {**value, "proposal_token": seal(provenance, "proposal")}
    if settings.authoring_provider == "openai":
        import httpx

        from app.ai.remote_chat import chat

        value, metadata = await chat(
            base=settings.authoring_service_url,
            key=settings.authoring_service_api_key,
            model=settings.authoring_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"scope": body.scope.model_dump(), "evidence": evidence}, ensure_ascii=False
                    ),
                },
            ],
            max_tokens=1600,
            timeout=httpx.Timeout(None, connect=5),
        )
        value = validate_proposal(value, evidence, body.scope.max_score)
        provenance = {
            "version": VERSION,
            "mode": "remote_openai",
            "model_metadata": metadata,
            "scope": body.scope.model_dump(),
            "selected_ids": body.selected_ids,
            "proposal": value,
        }
        return {**value, "proposal_token": seal(provenance, "proposal")}
    from urllib.parse import urlsplit

    import httpx

    url = urlsplit(settings.authoring_service_url)
    is_local = url.scheme == "http" and url.hostname in {
        "127.0.0.1",
        "localhost",
        "host.docker.internal",
    }
    from app.ai.remote_chat import configured

    remote = settings.authoring_provider == "service_http"
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or not url.hostname
        or (
            remote and (url.scheme != "https" or not configured(settings.authoring_service_api_key))
        )
        or (not remote and not is_local)
    ):
        raise HTTPException(503, "Invalid authoring service URL or missing authentication")
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5), trust_env=False) as client:
        response = await client.post(
            settings.authoring_service_url.rstrip("/") + "/authoring/propose",
            headers={"X-API-Key": settings.authoring_service_api_key} if remote else {},
            json={
                "version": VERSION,
                "system": SYSTEM,
                "scope": body.scope.model_dump(),
                "evidence": evidence,
            },
        )
    if response.status_code != 200:
        raise HTTPException(response.status_code, "Local authoring worker rejected request")
    value = validate_proposal(response.json(), evidence, body.scope.max_score)
    provenance = {
        "version": VERSION,
        "mode": "remote_service" if remote else "local_base_model",
        "scope": body.scope.model_dump(),
        "selected_ids": body.selected_ids,
        "proposal": value,
    }
    return {**value, "proposal_token": seal(provenance, "proposal")}


def approved_payload(question, answer):
    package = copy.deepcopy((question.import_metadata or {}).get("approved_package"))
    if not package:
        raise HTTPException(422, "Approved grading package is missing")
    check = package.pop("sha256")
    if digest(package) != check:
        raise HTTPException(422, "Approved grading package integrity failure")
    payload = package["payload"]
    payload["student_answer"] = answer
    return payload, package
