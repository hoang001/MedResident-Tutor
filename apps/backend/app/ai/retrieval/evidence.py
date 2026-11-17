"""Evidence identities and integrity checks shared by practice and integration tests."""

import hashlib
import json
from dataclasses import dataclass


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_identities(evidence):
    return [
        {
            "source_unit_id": e["source_unit_id"],
            "source_id": e["source_id"],
            "page_start": e["page_start"],
            "page_end": e["page_end"],
            "content_sha256": content_hash(e["content"]),
        }
        for e in evidence
    ]


def verify_payload_evidence(payload, trace):
    actual = evidence_identities(payload["evidence"])
    if actual != trace["selected_evidence"]:
        raise ValueError("RETRIEVAL_PAYLOAD_EVIDENCE_MISMATCH")
    return actual


@dataclass
class EvidenceBundle:
    evidence: list
    provenance: list
    trace: dict


def prelinked_trace(evidence, trace_id, requested="prelinked", reason=None):
    return {
        "trace_id": trace_id,
        "requested_strategy": requested,
        "effective_strategy": "prelinked",
        "data_source": "postgresql_source_units",
        "vector_search": False,
        "neo4j_queries": 0,
        "kg_contributed": False,
        "concept_ids": [],
        "kg_node_ids": [],
        "candidate_count": len(evidence),
        "selected_evidence": evidence_identities(evidence),
        "fallback_reason": reason,
        "retrieval_seconds": 0.0,
        "status": "prelinked_source_evidence",
        "adequacy": "prelinked_unadjudicated",
    }


def unavailable_bundle(question_id, trace_id, strategy, error_type):
    return EvidenceBundle(
        [],
        [],
        {
            "trace_id": trace_id,
            "question_id": question_id,
            "requested_strategy": strategy,
            "effective_strategy": "none",
            "data_source": "unavailable",
            "status": "insufficient_evidence",
            "adequacy": "unavailable",
            "selected_evidence": [],
            "concept_ids": [],
            "kg_node_ids": [],
            "neo4j_queries": 0,
            "vector_queries": 0,
            "vector_search": False,
            "kg_contributed": False,
            "candidate_count": 0,
            "retrieval_seconds": 0,
            "fallback_reason": "RETRIEVAL_UNAVAILABLE:" + error_type,
            "failure_code": "RETRIEVAL_UNAVAILABLE",
        },
    )
