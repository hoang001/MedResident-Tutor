"""Inventory existing extraction; resume imports only for explicitly reviewed overlays.

Does not call LLM, modify extraction/registry, or approve unseen records.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from document_toolkit.common import fingerprint, read_json, write_json
from knowledge_pipeline.kg_v2.neo4j_import import import_review

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/knowledge-extraction/v2/source-review-20261102"


def safe_json(path, default=None):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return default


def inventory():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    runs = []
    snapshots = {}
    for year in [2006, 2021]:
        name = (
            "book-2006-full-plan.json"
            if year == 2006
            else "book-2021-all-lessons-plan.json"
        )
        plan = read_json(ROOT / "knowledge_pipeline/kg_v2" / name)
        batch = ROOT / f"data/knowledge-extraction/v2/book-{year}-full-wait"
        state = safe_json(batch / "batch-state.json", {})
        snapshots[str(year)] = {"state": state, "plan": plan}
        for chapter in plan["chapters"]:
            number = chapter["lesson_number"]
            shards = [r for r in plan["shards"] if r["lesson_number"] == number]
            nodes = {}
            edges = {}
            done = set()
            partial = set()
            failed = set()
            rejected = []
            review_count = 0
            selected = []
            expected = chapter.get("windows", 0)
            if year == 2006 and number == 15:
                parent = (
                    ROOT
                    / "data/knowledge-extraction/v2/chapter-shoulder-2006-source-review-20261102"
                )
                g = read_json(parent / "graph.json")
                m = read_json(parent / "import-manifest.json")
                rows.append(
                    {
                        "book_year": year,
                        "lesson_number": number,
                        "title": chapter["title"],
                        "pdf_pages": chapter["pdf_pages"],
                        "lineage_selection": "source-compared overlay supersedes recovered aggregate and all earlier shoulder trials",
                        "selected_sources": [parent.relative_to(ROOT).as_posix()],
                        "expected_windows": 9,
                        "processed_windows": 9,
                        "partial_windows": 3,
                        "failed_windows": 0,
                        "not_processed_windows": 0,
                        "nodes_before": len(g["nodes"]),
                        "edges_before": len(g["edges"]),
                        "review_status": "source_compared_and_previously_imported",
                        "import_status": m["status"],
                        "review_directory": parent.relative_to(ROOT).as_posix(),
                        "pending_note": "Kocher held; pending equivalence retained separately.",
                    }
                )
                continue
            if year == 2006 and number == 16:
                b = ROOT / "data/knowledge-extraction/v2/chapter-elbow-2006-wait"
                s = read_json(b / "batch-state.json")
                selected = [ROOT / s["latest_aggregate"]]
                expected = 9
            else:
                # Snapshot only finalized shard reports. Do not consume a changing
                # in-flight shard as a source-reviewed/import-ready result.
                selected = [
                    batch / "shards" / s["key"]
                    for s in shards
                    if (batch / "shards" / s["key"] / "audit/report.json").exists()
                ]
            for folder in selected:
                g = safe_json(folder / "graph.json")
                report = safe_json(folder / "audit/report.json")
                windows = safe_json(folder / "audit/windows.json")
                if g is None or report is None or windows is None:
                    continue
                nodes.update({n["id"]: n for n in g["nodes"]})
                edges.update({e["id"]: e for e in g["edges"]})
                partial.update(report.get("partial_schema_windows", []))
                for w in windows:
                    if (folder / "audit/raw" / (w["window_id"] + ".json")).exists():
                        done.add(w["window_id"])
                failed.update(
                    r["window_id"]
                    for r in report.get("failed_windows", [])
                    if r.get("window_id") not in done
                )
                rejected.extend(safe_json(folder / "audit/rejected.json", []))
                review_count += report.get("review_items", 0)
            key = f"{year}-bai-{number:02d}"
            progress = (
                safe_json(OUT / "progress.json", {}).get("chapters", {}).get(key, {})
            )
            rows.append(
                {
                    "book_year": year,
                    "lesson_number": number,
                    "title": chapter["title"],
                    "pdf_pages": chapter["pdf_pages"],
                    "selected_sources": [
                        p.relative_to(ROOT).as_posix() for p in selected
                    ],
                    "lineage_selection": "final complete-scope shards from the book plan; exclude overlapping trials/revalidations",
                    "expected_windows": expected,
                    "processed_windows": len(done),
                    "complete_schema_windows": len(done - partial),
                    "partial_windows": len(partial),
                    "failed_windows": len(failed),
                    "not_processed_windows": max(0, expected - len(done) - len(failed)),
                    "nodes_before": len(nodes),
                    "edges_before": len(edges),
                    "review_records": review_count,
                    "rejected_records": len(rejected),
                    "source_opening_missing": chapter.get(
                        "source_opening_missing", False
                    ),
                    "review_status": progress.get("review_status", "not_reviewed"),
                    "import_status": progress.get("import_status", "not_imported"),
                    "review_directory": progress.get("review_directory"),
                    "snapshot_may_be_incomplete": len(done) < expected,
                }
            )
    for folder in sorted((ROOT / "data/knowledge-extraction/v2").iterdir()):
        if not folder.is_dir() or folder == OUT:
            continue
        manifest = safe_json(folder / "audit/manifest.json", {})
        runs.append(
            {
                "path": folder.relative_to(ROOT).as_posix(),
                "mode": manifest.get("mode"),
                "parents": manifest.get("parents", []),
                "nested_manifest_paths": [
                    p.relative_to(ROOT).as_posix()
                    for p in sorted(folder.rglob("manifest.json"))
                ],
                "lineage_note": "Recovery, offline revalidation and checkpoint repair directories are not extra chapters. Current final shards include the 2006 repair; shoulder source-review supersedes earlier shoulder extraction.",
                "role": "primary_book_run_or_imported_overlay"
                if folder.name
                in {
                    "book-2006-full-wait",
                    "book-2021-full-wait",
                    "chapter-elbow-2006-wait",
                    "chapter-shoulder-2006-source-review-20261102",
                }
                else "historical_trial_or_revalidation_not_added_to_primary_counts",
            }
        )
    for name in [
        "trial-20261027-llm",
        "trial-20261027-probes",
        "trial-20261028-graduate",
        "draft-work-20261030",
    ]:
        folder = ROOT / "data/knowledge-extraction" / name
        if folder.exists():
            runs.append(
                {
                    "path": folder.relative_to(ROOT).as_posix(),
                    "role": "legacy_trial_not_added_to_v2_primary_counts",
                    "lineage_note": "Pre-v2 demo/trial: not a source-reviewed replacement for book-plan shards.",
                }
            )
    stamp = datetime.now(UTC).isoformat()
    write_json(
        OUT / "inventory.json",
        {
            "snapshot_at_utc": stamp,
            "chapters": rows,
            "lineage_runs": runs,
            "counts_not_summed_across_overlapping_runs": True,
        },
    )
    write_json(OUT / "audit/batch-snapshots.json", snapshots)
    gaps = []
    for year in [2006, 2021]:
        prep = (
            ROOT
            / "data/knowledge-extraction"
            / (
                "book-2006-full-preparation-20261102"
                if year == 2006
                else "book-2021-preparation-20261102"
            )
        )
        for item in safe_json(prep / "excluded-lines.json", []):
            if item.get("reason") == "numbered_figure_caption":
                reviewed_caption = year == 2006 and item.get("pdf_page") in {12, 13}
                gaps.append(
                    {
                        "book_year": year,
                        **item,
                        "issue": "printed_caption_requires_semantic_pdf_review_not_automatically_outside_kg",
                        "review_status": "pdf_viewed_source_retained_in_lesson_02_audit"
                        if reviewed_caption
                        else "not_reviewed",
                    }
                )
    write_json(OUT / "caption-review-queue.json", gaps)
    write_json(
        OUT / "need-extraction.json",
        [
            {
                "book_year": r["book_year"],
                "lesson_number": r["lesson_number"],
                "pages": r["pdf_pages"],
                "failed_windows": r.get("failed_windows", 0),
                "unprocessed_windows": r.get("not_processed_windows", 0),
                "source_opening_missing": r.get("source_opening_missing", False),
            }
            for r in rows
            if r.get("failed_windows")
            or r.get("not_processed_windows")
            or r.get("source_opening_missing")
        ],
    )
    text = [
        "# Source review inventory\n",
        f"Snapshot UTC: {stamp}. Counts are snapshots, not review approval.\n",
        "| Book | Lesson | Pages PDF | Windows processed/expected | Partial | Nodes/edges before | Review/import |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        pages = r["pdf_pages"]
        text.append(
            f"| {r['book_year']} | {r['lesson_number']}. {r['title']} | {pages['start']}–{pages['end']} | {r['processed_windows']}/{r['expected_windows']} | {r['partial_windows']} | {r['nodes_before']}/{r['edges_before']} | {r['review_status']} / {r['import_status']} |"
        )
    (OUT / "inventory.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return rows


def apply_ready():
    state = safe_json(OUT / "progress.json", {"chapters": {}})
    for path in sorted((OUT / "chapters").glob("*/review-manifest.json")):
        chapter = read_json(path)
        key = path.parent.name
        if chapter.get("review_status") != "source_compared_records_separated":
            continue
        graph = path.parent / "graph.json"
        if fingerprint(read_json(graph)) != chapter["graph_fingerprint"]:
            raise ValueError("review_graph_changed_after_decisions")
        previous = state["chapters"].get(key, {})
        if (
            previous.get("import_status") == "imported_and_idempotency_verified"
            and previous.get("graph_fingerprint") == chapter["graph_fingerprint"]
        ):
            continue
        index = 1
        while (path.parent / f"import-{index:03d}").exists():
            index += 1
        first = import_review(graph, path.parent / f"import-{index:03d}", apply=True)
        second = import_review(
            graph, path.parent / f"import-{index + 1:03d}", apply=True
        )
        assert not any(
            second["counts"][k].get(action, 0)
            for k in ["nodes", "edges"]
            for action in ["create", "update"]
        )
        state["chapters"][key] = {
            **chapter,
            "review_directory": path.parent.relative_to(ROOT).as_posix(),
            "import_status": "imported_and_idempotency_verified",
            "first_import": first["counts"],
            "second_import": second["counts"],
            "first_manifest": (path.parent / f"import-{index:03d}/import-manifest.json")
            .relative_to(ROOT)
            .as_posix(),
            "idempotency_manifest": (
                path.parent / f"import-{index + 1:03d}/import-manifest.json"
            )
            .relative_to(ROOT)
            .as_posix(),
        }
        write_json(OUT / "progress.json", state)
        print(
            json.dumps(
                {
                    "chapter": key,
                    "first_import": first["counts"],
                    "idempotency": second["counts"],
                },
                ensure_ascii=True,
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Refresh inventory and use existing explicit review manifests",
    )
    parser.add_argument(
        "--apply-ready",
        action="store_true",
        help="Import only graph-fingerprinted, explicitly reviewed overlays",
    )
    args = parser.parse_args()
    if args.apply_ready:
        apply_ready()
    rows = inventory()
    print(
        json.dumps(
            {
                "chapters_in_inventory": len(rows),
                "source_review_workspace": str(OUT),
                "new_llm_calls": 0,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
