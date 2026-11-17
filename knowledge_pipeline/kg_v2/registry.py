"""Durable canonical UUID registry; source candidates require explicit identity decisions."""

from copy import deepcopy
from uuid import uuid4

from document_toolkit.common import fingerprint, read_json, write_json


def load_registry(path):
    return (
        read_json(path)
        if path.is_file()
        else {
            "version": "canonical-registry-v1",
            "entities": {},
            "bindings": {},
            "decisions": [],
        }
    )


def approve_decisions(path, candidates, decisions):
    registry = deepcopy(load_registry(path))
    nodes = {n["id"]: n for n in candidates["nodes"]}
    approved = [d for d in decisions if d.get("approved") is True]
    for d in approved:
        ids = d["candidate_ids"]
        if not ids or not d.get("basis") or any(i not in nodes for i in ids):
            raise ValueError("identity_decision_requires_existing_candidates_and_basis")
        types = {nodes[i]["type"] for i in ids}
        if len(types) != 1:
            raise ValueError("canonical_merge_requires_same_type")
        kind = next(iter(types))
        old = {registry["bindings"][i] for i in ids if i in registry["bindings"]}
        if len(old) > 1:
            raise ValueError("merging_existing_canonicals_requires_separate_migration")
        cid = d.get("existing_id") or (next(iter(old)) if old else None)
        if cid and (
            cid not in registry["entities"] or registry["entities"][cid]["type"] != kind
        ):
            raise ValueError("canonical_identity_type_mismatch")
        if cid is None:
            cid = (
                "SK_"
                if kind == "Skill"
                else "SQ_"
                if kind == "SampleQuestion"
                else "MC_"
            ) + uuid4().hex
            sample = nodes[ids[0]]
            registry["entities"][cid] = {
                "id": cid,
                "type": kind,
                "name": d.get("name", sample.get("name")),
                "aliases": d.get("aliases", sample.get("aliases", [])),
                "scope": None,
            }
        for i in ids:
            if i in registry["bindings"] and registry["bindings"][i] != cid:
                raise ValueError("cannot_rebind_candidate_silently")
            registry["bindings"][i] = cid
        d["canonical_id"] = cid
    # Resolve semantic context after all entities have durable IDs. Scope is not a book/page.
    for d in approved:
        cid = d["canonical_id"]
        entity = registry["entities"][cid]
        context = d.get("context")
        if entity["type"] == "ClassificationCategory" and not context:
            raise ValueError("category_identity_requires_system_and_subject")
        if context:
            mapped = {}
            for key in ("system_candidate_id", "subject_candidate_id"):
                if key in context:
                    ref = registry["bindings"].get(context[key])
                    if ref is None:
                        raise ValueError("canonical_context_not_resolved")
                    expected = (
                        "Classification"
                        if key == "system_candidate_id"
                        else "Condition"
                    )
                    if registry["entities"][ref]["type"] != expected:
                        raise ValueError("invalid_canonical_scope_type")
                    mapped[key.replace("_candidate", "")] = ref
            if entity["type"] == "ClassificationCategory":
                if set(mapped) != {"system_id", "subject_id"} or not context.get(
                    "level"
                ):
                    raise ValueError("category_scope_incomplete")
                mapped["level"] = context["level"]
            if entity["scope"] is not None and entity["scope"] != mapped:
                raise ValueError("different_classification_systems_must_not_merge")
            entity["scope"] = mapped
        record = {k: v for k, v in d.items() if k != "approved"}
        if record not in registry["decisions"]:
            registry["decisions"].append(record)
    write_json(path, registry)
    return registry


def resolve_graph(candidates, registry):
    nodes, mapping, pending = {}, {}, []
    for candidate in candidates["nodes"]:
        cid = registry["bindings"].get(candidate["id"])
        if not cid:
            pending.append(
                {
                    "candidate_id": candidate["id"],
                    "reason": "canonical_identity_not_reviewed",
                    "candidate": candidate,
                }
            )
            continue
        entity = registry["entities"][cid]
        if entity["type"] != candidate["type"]:
            raise ValueError("registry_type_mismatch")
        node = deepcopy(candidate)
        node["id"] = cid
        if "name" in node:
            node["name"] = entity["name"]
        if "aliases" in node:
            node["aliases"] = list(entity["aliases"])
        if node["type"] == "ClassificationCategory":
            scope = entity["scope"]
            if (
                not scope
                or scope.get("system_id") not in registry["entities"]
                or scope.get("subject_id") not in registry["entities"]
            ):
                raise ValueError("category_registry_scope_missing")
            original = candidate["name"]
            node["name"] = " — ".join(
                [
                    registry["entities"][scope["subject_id"]]["name"],
                    registry["entities"][scope["system_id"]]["name"],
                    scope["level"],
                ]
            )
            if original not in node["aliases"]:
                node["aliases"].append(original)
        if cid in nodes:
            if "content" in node:
                for content in node["content"]:
                    if content not in nodes[cid]["content"]:
                        nodes[cid]["content"].append(content)
                nodes[cid]["content"].sort(key=fingerprint)
        else:
            nodes[cid] = node
        mapping[candidate["id"]] = cid
    edges = {}
    for edge in candidates["edges"]:
        if edge["from_id"] not in mapping or edge["to_id"] not in mapping:
            pending.append(
                {
                    "edge_id": edge["id"],
                    "reason": "edge_has_unresolved_canonical_endpoint",
                }
            )
            continue
        value = {
            **deepcopy(edge),
            "from_id": mapping[edge["from_id"]],
            "to_id": mapping[edge["to_id"]],
        }
        value.pop("id")
        value["id"] = "KG2E_" + fingerprint(value)[:24]
        edges[value["id"]] = value
    graph = {
        "schema_version": candidates["schema_version"],
        "nodes": [nodes[k] for k in sorted(nodes)],
        "edges": [edges[k] for k in sorted(edges)],
    }
    return graph, {
        "candidate_to_canonical": mapping,
        "pending_identity_review": pending,
        "registry_snapshot": registry,
    }
