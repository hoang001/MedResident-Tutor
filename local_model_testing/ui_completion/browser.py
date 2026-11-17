import json
import os
import subprocess
import sys
from urllib.parse import quote
from .common import ROOT,RUN,DOCKER

def main():
    info=json.loads(subprocess.check_output([DOCKER,'inspect','medresident-tutor-backend-1']))[0]
    env=dict(e.split('=',1) for e in info['Config']['Env'])
    dbinfo=json.loads(subprocess.check_output([DOCKER,'inspect','medresident-tutor-db-1']))[0]
    db=dict(e.split('=',1) for e in dbinfo['Config']['Env'])
    name='medresident_test_ui_completion_20261116'
    assert name == 'medresident_test_ui_completion_20261116'
    subprocess.run([DOCKER,'exec','medresident-tutor-db-1','dropdb','--if-exists','--force','-U',db['POSTGRES_USER'],name],capture_output=True,check=True)
    created=subprocess.run([DOCKER,'exec','medresident-tutor-db-1','createdb','-U',db['POSTGRES_USER'],name],capture_output=True)
    if created.returncode==0:
        dump=subprocess.check_output([DOCKER,'exec','medresident-tutor-db-1','pg_dump','-U',db['POSTGRES_USER'],'-d',db['POSTGRES_DB'],'-Fc'])
        restore=subprocess.run([DOCKER,'exec','-i','medresident-tutor-db-1','pg_restore','-U',db['POSTGRES_USER'],'-d',name,'--no-owner'],input=dump,capture_output=True)
        assert restore.returncode==0
    env.update(DATABASE_URL=f"postgresql+asyncpg://{quote(db['POSTGRES_USER'])}:{quote(db['POSTGRES_PASSWORD'])}@db:5432/{name}",
        PYTHONPATH='/workspace/apps/backend:/workspace/model-training:/workspace',FILE_STORAGE_PATH='/workspace/data/uploads',
        KNOWLEDGE_DATA_ROOT='/workspace/data',PRACTICE_PROVIDER='mock',MODEL_CALLS_ENABLED='false',AUTHORING_PROVIDER='off',
        CORS_ORIGINS='http://host.docker.internal:3000')
    cmd=[DOCKER,'run','--rm','-d','--name','medresident-ui-completion-api','--network',next(iter(info['NetworkSettings']['Networks'])),
        '--mount',f'type=bind,source={ROOT},target=/workspace','--mount',f'type=bind,source={ROOT / "data"},target=/app/data',
        '-w','/workspace','-p','127.0.0.1:8106:8106']
    for key in env: cmd+=['-e',key]
    cmd+=['medresident-tutor-backend:latest','python','-m','uvicorn','local_model_testing.ui_completion.browser_app:app','--host','0.0.0.0','--port','8106','--no-access-log']
    subprocess.run(cmd,env={**os.environ,**env},check=True,capture_output=True)
    phase='before' if '--before' in sys.argv else 'after'
    try:
        result=subprocess.run([DOCKER,'run','--rm','--name','medresident-ui-completion-browser','--mount',f'type=bind,source={ROOT},target=/workspace',
            '-w','/workspace/apps/frontend','-e','UI_PHASE='+phase,'mcr.microsoft.com/playwright:v1.56.1-noble','sh','-c',
            'node node_modules/@playwright/test/cli.js test --config playwright.ui-completion.config.ts'],capture_output=True)
        out=(result.stdout+result.stderr).decode(errors='replace')
        (RUN/('browser-'+phase+'.log')).write_text(out,encoding='utf-8')
        print(out[-5000:].encode('ascii','backslashreplace').decode())
        if result.returncode:
            logs=subprocess.check_output([DOCKER,'logs','medresident-ui-completion-api'],stderr=subprocess.STDOUT).decode(errors='replace')
            for k,v in env.items():
                if v and any(w in k for w in ('PASSWORD','KEY','SECRET','URL')): logs=logs.replace(v,'[REDACTED]')
            (RUN/('browser-api-'+phase+'.log')).write_text(logs,encoding='utf-8')
        raise SystemExit(result.returncode)
    finally: subprocess.run([DOCKER,'stop','medresident-ui-completion-api'],capture_output=True)

if __name__=='__main__':main()
