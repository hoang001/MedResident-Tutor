"""Run from repo root: python -m knowledge_pipeline --help."""

import argparse
from pathlib import Path

from document_toolkit.common import read_json, write_json
from document_toolkit.config import DEFAULT_ENV_FILE, Settings

from .pipeline import check_output, extract, inventory, prepare, prepare_source_probes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "dry-run", "extract"])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--scope",
        type=Path,
        default=Path("knowledge_pipeline/scopes/two-books-trial.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/knowledge-extraction")
    )
    parser.add_argument("--chunk-bytes", type=int, default=18000)
    parser.add_argument("--source-probes-only", action="store_true",
                        help="Extract only exact surveyed source excerpts, not entire trial pages")
    parser.add_argument("--tessdata", type=Path)
    parser.add_argument("--ocr-json-dir", type=Path,
                        help="Use existing page OCR JSON files, without running OCR again")
    parser.add_argument(
        "--ocr-python",
        type=Path,
        help="Existing trusted Python with PyMuPDF; local subprocess callback",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Shared repository .env (or an explicitly selected file)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--resume", action="store_true")
    group.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        root = args.repo_root.resolve()
        config = read_json(args.scope)
        output = check_output(root, args.output)
        if args.command == "inventory":
            rows = inventory(root, config, output)
            print("Inventory:", len(rows), "documents; OCR/LLM not called")
            return 0
        callback, metadata = None, None
        if args.ocr_json_dir:
            if args.tessdata or args.ocr_python:
                raise ValueError("Choose supplied OCR JSON or a live OCR runtime, not both")
            from .ocr import provided_ocr_json

            callback, metadata = provided_ocr_json(root, config["documents"], args.ocr_json_dir)
        if args.tessdata:
            if args.ocr_python:
                from .ocr import subprocess_ocr

                callback, metadata = subprocess_ocr(args.ocr_python, args.tessdata)
            else:
                from .ocr import local_ocr

                callback, metadata = local_ocr(args.tessdata)
        prepared, report = prepare(
            root,
            config,
            output,
            ocr_page=callback,
            ocr_metadata=metadata,
            chunk_bytes=args.chunk_bytes,
        )
        if args.command == "dry-run" or args.source_probes_only:
            from .survey import export_survey

            _, probes = export_survey(config, output)
            if args.source_probes_only:
                prepared = prepare_source_probes(
                    prepared, probes, output, chunk_bytes=args.chunk_bytes,
                )
        if args.command == "dry-run":
            # Empty files honestly represent no medical extraction, not synthetic LLM output.
            target = output / "raw" / "dry-run-candidates"
            target.mkdir(parents=True, exist_ok=True)
            for name in ("source_units", "concept_candidates", "medical_statements"):
                (target / (name + ".jsonl")).write_text("", encoding="utf-8")
            write_json(
                target / "status.json",
                {
                    "status": "not_extracted",
                    "llm_called": False,
                    "expert_review": "unverified",
                },
            )
            print("Dry run: no LLM called; inspect dry-run-report.json")
            return int(any(d["unreadable_pages"] for d in report["documents"]))
        if args.env_file is None or not args.env_file.is_file():
            raise ValueError("Provide an explicit existing extraction --env-file")
        result = extract(
            prepared,
            output,
            settings=Settings.from_env(args.env_file),
            resume=args.resume,
            force=args.force,
            chunk_bytes=args.chunk_bytes,
        )
        print(
            "Extraction:",
            result["status"],
            result["counts"],
            "expert review: unverified",
        )
        return int(result["status"] != "complete_scope")
    except Exception as exc:
        # Avoid logging endpoint URLs, credentials, medical source dumps or LLM response bodies.
        print(
            "Failed:",
            type(exc).__name__,
            "(check configuration, source scope and validation reports)",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
