"""Portable CLI. Reading does not require a model, API key or network."""
import argparse
import logging
from pathlib import Path

from .common import read_json,write_json
from .config import Settings
from .documents import read_document,chunk_sections
from .pipeline import extract_document


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    read=commands.add_parser('read',help='Read PDF/JSON/JSONL into text chunks with source references')
    extract=commands.add_parser('extract',help='Extract JSON using YOUR prompt/schema; optional judge')
    for command in (read,extract):
        command.add_argument('--input',type=Path,required=True)
        command.add_argument('--output',type=Path,required=True)
        command.add_argument('--chunk-bytes',type=int,default=6000)
    extract.add_argument('--prompt',type=Path,required=True)
    extract.add_argument('--schema',type=Path,required=True)
    extract.add_argument('--judge-prompt',type=Path)
    extract.add_argument('--judge-schema',type=Path)
    extract.add_argument('--env-file',type=Path,default=Path('.env'))
    restart=extract.add_mutually_exclusive_group()
    restart.add_argument('--continue',dest='resume',action='store_true')
    restart.add_argument('--force',action='store_true')
    args=parser.parse_args()
    if args.chunk_bytes<4:parser.error('--chunk-bytes must be at least 4')
    if args.command=='extract' and args.judge_schema and not args.judge_prompt:
        parser.error('--judge-schema requires --judge-prompt')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        if args.command=='read':
            if args.input.resolve()==args.output.resolve():raise ValueError('Output must not overwrite input')
            document=read_document(args.input)
            chunks=chunk_sections(document['sections'],args.chunk_bytes)
            write_json(args.output,{**document,'sections':chunks})
            print(f'Read chunks={len(chunks)} unreadable_pages={document["unreadable_pages"]} output={args.output}')
            return int(bool(document['unreadable_pages']) or not chunks)
        result=extract_document(args.input,args.output,settings=Settings.from_env(args.env_file),
            prompt=args.prompt.read_text(encoding='utf-8'),schema=read_json(args.schema),
            judge_prompt=args.judge_prompt.read_text(encoding='utf-8') if args.judge_prompt else None,
            judge_schema=read_json(args.judge_schema) if args.judge_schema else None,
            max_chunk_bytes=args.chunk_bytes,resume=args.resume,force=args.force)
        print(f'{result["status"]}: chunks={result["completed_chunks"]}/{result["total_chunks"]} output={args.output}')
        return int(result['status']!='complete')
    except KeyboardInterrupt:
        print('Stopped. Rerun with --continue to reuse saved calls.');return 130
    except Exception as exc:
        # Avoid printing HTTP exceptions containing credentials or request bodies.
        print(f'Failed: {exc}' if isinstance(exc,ValueError) else f'Failed: {type(exc).__name__}')
        return 1


if __name__=='__main__':raise SystemExit(main())
