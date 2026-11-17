import argparse
import json
from pathlib import Path

from document_toolkit.common import read_json, write_json

from .loader import dry_run_loader
from .pipeline import ROOT, run


def main():
    parser = argparse.ArgumentParser(
        description="Content-only medical KG v2; never writes Neo4j"
    )
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "extract",
            "loader-dry-run",
            "revalidate",
            "batch",
            "recover",
        ],
    )
    parser.add_argument("--input-run", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--identity-decisions", type=Path)
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Export sourced draft IDs and external review queues",
    )
    parser.add_argument("--draft-registry", type=Path)
    parser.add_argument("--attempts-per-window", type=int, default=2)
    parser.add_argument(
        "--scope", type=Path, default=ROOT / "knowledge_pipeline/kg_v2/trial-scope.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/knowledge-extraction/v2/trial-20261029",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-calls", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--total-seconds", type=int, default=360)
    parser.add_argument(
        "--no-response-timeout",
        action="store_true",
        help="Draft/batch: disable response/write/pool timeouts and total wait budget",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=30,
        help="Connection establishment timeout in seconds in no-response-timeout mode",
    )
    args = parser.parse_args()
    try:
        if args.command == "recover":
            if args.input_run is None:
                raise ValueError("input_run_required")
            from .recovery import recover_batch

            report = recover_batch(
                args.input_run, args.output, draft_registry_path=args.draft_registry
            )
        elif args.command == "batch":
            from .batch import run_batch

            report = run_batch(
                args.scope,
                args.output,
                max_calls=args.max_calls,
                total_seconds=args.total_seconds,
                timeout_seconds=args.timeout,
                resume=args.resume,
                draft_registry_path=args.draft_registry,
                attempts_per_window=args.attempts_per_window,
                no_response_timeout=args.no_response_timeout,
                connect_timeout_seconds=args.connect_timeout,
            )
        elif args.command == "revalidate":
            if args.input_run is None:
                raise ValueError("input_run_required")
            from .revalidate import revalidate

            report = revalidate(
                args.input_run,
                args.output,
                registry_path=args.registry,
                decisions_path=args.identity_decisions,
                draft=args.draft,
                draft_registry_path=args.draft_registry,
            )
        elif args.command == "loader-dry-run":
            payload = dry_run_loader(read_json(args.output / "graph.json"))
            write_json(args.output / "audit/loader-preview.json", payload)
            report = {
                "mode": payload["mode"],
                "nodes": len(payload["nodes"]),
                "edges": len(payload["edges"]),
                "neo4j_imported": False,
            }
        else:
            report = run(
                args.scope,
                args.output,
                resume=args.resume,
                dry_run=args.command == "prepare",
                max_calls=args.max_calls,
                timeout_seconds=args.timeout,
                total_seconds=args.total_seconds,
                registry_path=args.registry,
                draft=args.draft,
                draft_registry_path=args.draft_registry,
                attempts_per_window=args.attempts_per_window,
                no_response_timeout=args.no_response_timeout,
                connect_timeout_seconds=args.connect_timeout,
            )
            if args.command == "extract":
                payload = dry_run_loader(read_json(args.output / "graph.json"))
                write_json(args.output / "audit/loader-preview.json", payload)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 -- sanitize any configuration/service error at CLI boundary
        # Do not print raw service exceptions, source dumps or settings.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
