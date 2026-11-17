"""CLI for manual collection; never connects to a model or project databases."""
import argparse
import json
import time
from datetime import UTC, datetime

from .build import build_cases, validate
from .graz import sample
from .io import DATA, Fetcher, write
from .pmc import discover, prepare
from .review import build_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("discover", help="Metadata only; does not create cases/exercises")
    search.add_argument("--per-group", type=int, default=15)
    get = commands.add_parser("prepare", help="Retrieve one licensed article XML for manual reading")
    get.add_argument("pmcid")
    commands.add_parser("collect", help="Resume the manually selected 10 cases and 20 imaging studies")
    commands.add_parser("validate", help="Offline schema/source/hash/grouping checks")
    commands.add_parser("review", help="Rebuild offline HTML and Markdown review")
    args = parser.parse_args()
    fetcher = Fetcher()
    started = time.monotonic()
    run = {"command": args.command, "started_at": datetime.now(UTC).isoformat(), "llm_calls": 0, "database_calls": 0}
    try:
        if args.command == "discover":
            result = {"candidate_count": len(discover(fetcher, args.per_group)), "downloaded_cases": 0}
        elif args.command == "prepare":
            parsed = prepare(fetcher, args.pmcid)
            result = {"pmcid": args.pmcid, "paragraphs": len(parsed["blocks"]), "figures": len(parsed["figures"])}
        elif args.command == "collect":
            build_cases(fetcher)
            sample(fetcher, 20)
            result = build_review()
        elif args.command == "validate":
            result = validate()
        else:
            result = build_review()
        run.update(status="success", result=result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        run.update(status="failed", error_type=type(exc).__name__, http_status=getattr(getattr(exc, "response", None), "status_code", None),
                   reason=str(exc) if type(exc) in (ValueError, KeyError) else None)
        print(json.dumps({k: run[k] for k in ("status", "error_type", "http_status", "reason")}, ensure_ascii=False))
        return 1
    finally:
        fetcher.client.close()
        run.update(network_requests=fetcher.calls, cache_hits=fetcher.cache_hits,
                   network_body_bytes=fetcher.bytes, elapsed_seconds=round(time.monotonic()-started, 3))
        path = DATA / "audit/runs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(run, ensure_ascii=False) + "\n")
        write(DATA / "audit/last-run.json", run)


if __name__ == "__main__":
    raise SystemExit(main())
