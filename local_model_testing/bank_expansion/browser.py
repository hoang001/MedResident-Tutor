import json
import os
import subprocess
from urllib.parse import quote

from .common import ROOT, RUN, DOCKER

def main():
    info=json.loads(subprocess.check_output([DOCKER,'inspect','medresident-tutor-db-1']))[0]
    cfg=dict(e.split('=',1) for e in info['Config']['Env'])
    network=next(iter(info['NetworkSettings']['Networks']))
    database='medresident_test_bank_browser_20261116'
    created=subprocess.run([DOCKER,'exec','medresident-tutor-db-1','createdb','-U',cfg['POSTGRES_USER'],database],capture_output=True)
    if created.returncode==0:
        dump=subprocess.check_output([DOCKER,'exec','medresident-tutor-db-1','pg_dump','-U',cfg['POSTGRES_USER'],'-d',cfg['POSTGRES_DB'],'-Fc'])
        restored=subprocess.run([DOCKER,'exec','-i','medresident-tutor-db-1','pg_restore','-U',cfg['POSTGRES_USER'],'-d',database,'--no-owner'],input=dump,capture_output=True)
        assert restored.returncode==0, 'Failed to restore named test copy'
    url=f"postgresql+asyncpg://{quote(cfg['POSTGRES_USER'])}:{quote(cfg['POSTGRES_PASSWORD'])}@db:5432/{database}"
    env={**os.environ,'DATABASE_URL':url}
    name='medresident-bank-browser'
    subprocess.run([DOCKER,'run','--rm','-d','--name',name,'--network',network,
        '--mount',f'type=bind,source={ROOT},target=/workspace','-w','/workspace','-p','127.0.0.1:8105:8105',
        '-e','DATABASE_URL','-e','PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/workspace',
        '-e','CORS_ORIGINS=http://host.docker.internal:3000','-e','PRACTICE_PROVIDER=mock','-e','MODEL_CALLS_ENABLED=false',
        '-e','AUTHORING_PROVIDER=off','-e','FILE_STORAGE_PATH=/workspace/data/uploads','-e','KNOWLEDGE_DATA_ROOT=/workspace/data',
        'medresident-tutor-backend:latest','python','-m','uvicorn','local_model_testing.bank_expansion.browser_app:app',
        '--host','0.0.0.0','--port','8105','--no-access-log'],env=env,check=True,capture_output=True)
    try:
        result=subprocess.run([DOCKER,'run','--rm','--name','medresident-bank-playwright','--mount',f'type=bind,source={ROOT},target=/workspace',
            '-w','/workspace/apps/frontend','mcr.microsoft.com/playwright:v1.56.1-noble','sh','-c',
            'node node_modules/@playwright/test/cli.js test --config playwright.bank-expansion.config.ts'],capture_output=True)
        out=(result.stdout+result.stderr).decode(errors='replace')
        (RUN/'browser.log').write_text(out,encoding='utf-8')
        print(out[-5000:].encode('ascii','backslashreplace').decode())
        if result.returncode:
            logs=subprocess.check_output([DOCKER,'logs',name],stderr=subprocess.STDOUT).decode(errors='replace')
            (RUN/'browser-backend.log').write_text(logs.replace(url,'[TEST_DATABASE]'),encoding='utf-8')
        raise SystemExit(result.returncode)
    finally: subprocess.run([DOCKER,'stop',name],capture_output=True)

if __name__=='__main__': main()
