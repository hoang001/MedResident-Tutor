import json
import os
import subprocess
from urllib.parse import quote

from .common import DOCKER, ROOT, RUN

def main():
    info=json.loads(subprocess.check_output([DOCKER,'inspect','medresident-tutor-db-1']))[0]
    cfg=dict(e.split('=',1) for e in info['Config']['Env'])
    name='medresident_test_bank_expansion_20261116'
    subprocess.run([DOCKER,'exec','medresident-tutor-db-1','createdb','-U',cfg['POSTGRES_USER'],name],capture_output=True)
    url=f"postgresql+asyncpg://{quote(cfg['POSTGRES_USER'])}:{quote(cfg['POSTGRES_PASSWORD'])}@db:5432/{name}"
    cmd=[DOCKER,'run','--rm','--name','medresident-bank-tests','--network',next(iter(info['NetworkSettings']['Networks'])),
         '--mount',f'type=bind,source={ROOT},target=/workspace','-w','/workspace/apps/backend','-e','INTEGRATION_TEST_DATABASE_URL',
         '-e','PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/tmp/checkdeps','-e','MODEL_CALLS_ENABLED=false',
         'medresident-tutor-backend:latest','sh','-c',
         'pip install -q --target /tmp/checkdeps pytest pytest-asyncio ruff aiosqlite numpy && '
         'PYTHONPATH=/tmp/checkdeps python -m ruff format app/modules/questions/publication.py app/modules/questions/router.py app/modules/practice/router.py postgres_tests/test_bank_expansion.py && '
         'PYTHONPATH=/tmp/checkdeps python -m ruff check app/modules/questions/publication.py app/modules/questions/router.py app/modules/practice/router.py postgres_tests/test_bank_expansion.py --fix && '
         'python -m pytest -q tests/test_authoring.py tests/test_practice_contracts.py tests/test_practice_retrieval.py tests/test_structured_practice.py postgres_tests/test_authoring_workflow.py postgres_tests/test_question_bank.py postgres_tests/test_bank_expansion.py --junitxml=/workspace/data/authoring/bank-expansion-20261116/tests.xml']
    result=subprocess.run(cmd,env={**os.environ,'INTEGRATION_TEST_DATABASE_URL':url},capture_output=True)
    out=(result.stdout+result.stderr).decode(errors='replace').replace(url,'[TEST_DATABASE]')
    (RUN/'tests.log').write_text(out,encoding='utf-8')
    print(out[-6000:].encode('ascii','backslashreplace').decode())
    raise SystemExit(result.returncode)

if __name__=='__main__': main()
