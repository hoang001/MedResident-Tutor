"""Exact guarded repair of our own reviewed OCR typo; no source/raw edits."""

import copy
import json
import shutil

from dotenv import dotenv_values
from neo4j import GraphDatabase
from summarize_kg_source_review import OUT, ROOT, jsonl

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.corrections import trace_raw
from knowledge_pipeline.kg_v2.loader import dry_run_loader
from knowledge_pipeline.kg_v2.neo4j_import import import_review, validate_locators
from knowledge_pipeline.neo4j_export import read_graph


def main():
    folder = OUT / "chapters/2006-bai-13"
    history = OUT / "remaining-2006/history/2006-bai-13-before-word-repair"
    if history.exists():
        raise ValueError("repair_already_prepared_inspect_checkpoint")
    shutil.copytree(folder, history)
    old_graph = read_json(folder / "graph.json")
    graph = copy.deepcopy(old_graph)
    before_word, after_word = "Chăm sốc", "Chăm sóc"
    pages = [
        json.loads(s)
        for s in (folder / "audit/pages.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    page = next(p for p in pages if p["pdf_page"] == 82)
    assert page["text"].count(before_word) == 1
    page["text"] = page["text"].replace(before_word, after_word)
    page["correction"]["corrected_text"] = page["text"]
    page["correction"]["revision"] = fingerprint(
        [page["raw_text"], page["text"], page["correction"]["segments"]]
    )
    locators = read_json(folder / "audit/locators.json")
    by_id = {r["locator_id"]: r for r in locators}
    changed_ids = []
    for n in graph["nodes"]:
        for c in n.get("content", []):
            for s in c["sources"]:
                if before_word not in s["excerpt"]:
                    continue
                prior = by_id[s["locator_id"]]
                new = copy.deepcopy(prior)
                s["excerpt"] = s["excerpt"].replace(before_word, after_word)
                lid = (
                    "LOCR_"
                    + fingerprint(
                        [
                            s["source_id"],
                            82,
                            prior["char_start"],
                            prior["char_end"],
                            page["correction"]["revision"],
                        ]
                    )[:24]
                )
                new.update(
                    {
                        "locator_id": lid,
                        "text": s["excerpt"],
                        **trace_raw(
                            page["correction"], prior["char_start"], prior["char_end"]
                        ),
                    }
                )
                assert new["corrected_text"] == s["excerpt"]
                s["locator_id"] = lid
                locators.append(new)
                changed_ids.append(n["id"])
            c["text"] = "\n".join(s["excerpt"] for s in c["sources"])
    assert changed_ids == ["DRN_a8b7b6caeedb55499efaf0368312a1f1"]
    old_node = next(n for n in old_graph["nodes"] if n["id"] == changed_ids[0])
    node = next(n for n in graph["nodes"] if n["id"] == changed_ids[0])
    props_old = next(
        r["properties"]
        for r in dry_run_loader(old_graph)["nodes"]
        if r["properties"]["id"] == node["id"]
    )
    props_new = next(
        r["properties"]
        for r in dry_run_loader(graph)["nodes"]
        if r["properties"]["id"] == node["id"]
    )
    jsonl(folder / "audit/pages.jsonl", pages)
    write_json(folder / "audit/locators.json", locators)
    assert validate_locators(graph, folder)
    env = dotenv_values(ROOT / ".env", interpolate=False, encoding="utf-8-sig")
    assert (
        env["NEO4J_URI"] == "bolt://localhost:7687" and env["NEO4J_DATABASE"] == "neo4j"
    )
    audit = folder / "word-repair"
    audit.mkdir()
    with (
        GraphDatabase.driver(
            env["NEO4J_URI"],
            auth=(env["NEO4J_USERNAME"], env["NEO4J_PASSWORD"]),
            connection_timeout=5,
            max_transaction_retry_time=0,
        ) as driver,
        driver.session(database=env["NEO4J_DATABASE"]) as session,
        session.begin_transaction(timeout=60) as tx,
    ):
        before = read_graph(tx, None)
        matches = [
            r for r in before["nodes"] if r["properties"].get("id") == node["id"]
        ]
        assert len(matches) == 1 and matches[0]["properties"] == props_old
        write_json(audit / "before-all.json", before)
        record = tx.run(
            "MATCH (n {id:$id}) WHERE n.content=$before SET n.content=$after RETURN n.id AS id",
            id=node["id"],
            before=props_old["content"],
            after=props_new["content"],
        ).single()
        assert record and record["id"] == node["id"]
        after = read_graph(tx, None)
        expected = copy.deepcopy(before)
        next(r for r in expected["nodes"] if r["properties"].get("id") == node["id"])[
            "properties"
        ]["content"] = props_new["content"]
        assert after == expected, "unexpected_record_change"
        tx.commit()
    write_json(audit / "after-all.json", after)
    write_json(
        audit / "decision.json",
        {
            "reason": "Đối chiếu lại ảnh PDF82: chăm sóc, không phải chăm sốc. Sửa lỗi của overlay sau kiểm cuối, không sửa OCR gốc.",
            "before": old_node,
            "after": node,
            "history": history.relative_to(ROOT).as_posix(),
            "changed_nodes": 1,
            "changed_edges": 0,
        },
    )
    write_json(folder / "graph.json", graph)
    jsonl(folder / "reviewed-nodes.jsonl", graph["nodes"])
    patches = read_json(folder / "ocr-patches.json")
    for r in patches:
        r["after"] = r["after"].replace(before_word, after_word)
    write_json(folder / "ocr-patches.json", patches)
    for name in ["review.html", "review.md"]:
        path = folder / name
        path.write_text(
            path.read_text(encoding="utf-8").replace(before_word, after_word),
            encoding="utf-8",
        )
    decisions = read_json(folder / "decisions.json")
    decisions.append(
        {
            "kind": "node",
            "id": node["id"],
            "decision": "correct",
            "before": old_node,
            "after": node,
            "reason": "Final exact-word repair, see word-repair/decision.json; previous overlay preserved in history.",
        }
    )
    write_json(folder / "decisions.json", decisions)
    manifest = read_json(folder / "review-manifest.json")
    manifest.update(
        {
            "graph_fingerprint": fingerprint(graph),
            "post_review_word_repair": "word-repair/decision.json",
        }
    )
    write_json(folder / "review-manifest.json", manifest)
    second = import_review(folder / "graph.json", folder / "import-003", apply=True)
    assert second["counts"] == {"nodes": {"skip": 58}, "edges": {"skip": 44}}
    progress = read_json(OUT / "progress.json")
    progress["chapters"]["2006-bai-13"].update(
        {
            "graph_fingerprint": fingerprint(graph),
            "post_review_word_repair": (audit / "decision.json")
            .relative_to(ROOT)
            .as_posix(),
            "idempotency_manifest": (folder / "import-003/import-manifest.json")
            .relative_to(ROOT)
            .as_posix(),
        }
    )
    write_json(OUT / "progress.json", progress)
    print(
        "Exact-word repair verified; 1 node content corrected, all other records unchanged; repeat import only skips."
    )


if __name__ == "__main__":
    main()
