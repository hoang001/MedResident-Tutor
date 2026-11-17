import asyncio
import json
import subprocess
import sys
import zipfile
from .common import ROOT,RUN,DOCKER,sha,digest,inside,write

async def baseline():
    import app.models  # noqa: F401
    from sqlalchemy import text
    from app.core.database import engine
    tables={}
    async with engine.connect() as c:
        await c.execute(text('SET TRANSACTION READ ONLY'))
        for table in ('users','questions','rubrics','rubric_criteria','rubric_criterion_source_units','source_units','documents','topics','specialties','practice_attempts','study_records','study_sessions','knowledge_reviews'):
            rows=(await c.execute(text('SELECT row_to_json(t)::text FROM '+table+' t'))).scalars().all()
            tables[table]=dict(count=len(rows),row_hashes=sorted(digest(json.loads(r)) for r in rows))
    write('database-before.json',tables)
    print({k:v['count'] for k,v in tables.items()})

def main():
    if '--inside' in sys.argv: return asyncio.run(baseline())
    archive=RUN/'code-before.zip'
    if not archive.exists():
        files=[]
        for folder in ('apps/frontend/app','apps/frontend/components','apps/frontend/lib','apps/frontend/e2e','apps/backend/app','docs/ui'):
            files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        files.extend(p for p in (ROOT/'apps/frontend').glob('*') if p.is_file() and p.suffix in ('.json','.ts','.mjs'))
        files.extend(p for p in (ROOT/'PRODUCT.md',ROOT/'DESIGN.md',ROOT/'.impeccable/design.json') if p.exists())
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in dict.fromkeys(files): z.write(p,p.relative_to(ROOT))
        write('code-before-hashes.json',{p.relative_to(ROOT).as_posix():sha(p) for p in dict.fromkeys(files)})
        protected=ROOT/'data/authoring/bank-expansion-20261116/protected-files.json'
        write('bank-and-locked-data-hashes.json',{
            **json.loads(protected.read_text(encoding='utf-8')),
            **{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'data/authoring/bank-expansion-20261116').glob('*.json')}
        })
    if not (RUN/'database-before.json').exists(): inside('prepare')
    git=subprocess.run([DOCKER,'run','--rm','--name','medresident-ui-git','--mount',f'type=bind,source={ROOT},target=/repo','-w','/repo',
        'node:22-bookworm-slim','sh','-c','apt-get update -qq && apt-get install -y -qq git >/dev/null && git -c safe.directory=/repo status --short'],capture_output=True)
    output=(git.stdout+git.stderr).decode(errors='replace')
    (RUN/'git-status-before.txt').write_text(output,encoding='utf-8')
    print('Code backup ready. git status exit:',git.returncode)

if __name__=='__main__': main()
