"""Run relevant regressions only in an explicitly named disposable database."""
import json
import os
import subprocess
from urllib.parse import quote

from .common import DOCKER, ROOT, RUN


def main():
    info = json.loads(subprocess.check_output([DOCKER, 'inspect', 'medresident-tutor-db-1']))[0]
    cfg = dict(e.split('=', 1) for e in info['Config']['Env'])
    name = 'medresident_test_ui_regression_20261116'
    subprocess.run([DOCKER, 'exec', 'medresident-tutor-db-1', 'createdb', '-U', cfg['POSTGRES_USER'], name], capture_output=True)
    url = f"postgresql+asyncpg://{quote(cfg['POSTGRES_USER'])}:{quote(cfg['POSTGRES_PASSWORD'])}@db:5432/{name}"
    targets = 'app/modules/questions/router.py app/modules/questions/service.py app/modules/practice/router.py postgres_tests/test_ui_workspace.py'
    script = ('pip install -q --target /tmp/checkdeps pytest pytest-asyncio ruff aiosqlite numpy && '
              f'PYTHONPATH=/tmp/checkdeps python -m ruff format {targets} && '
              f'PYTHONPATH=/tmp/checkdeps python -m ruff check {targets} --fix && '
              'python -m pytest -q tests/test_authoring.py tests/test_practice_contracts.py tests/test_practice_retrieval.py tests/test_structured_practice.py '
              'postgres_tests/test_authoring_workflow.py postgres_tests/test_question_bank.py postgres_tests/test_bank_expansion.py postgres_tests/test_ui_workspace.py '
              '--junitxml=/workspace/data/authoring/ui-completion-20261116/tests.xml')
    cmd = [DOCKER, 'run', '--rm', '--name', 'medresident-ui-regression', '--network', next(iter(info['NetworkSettings']['Networks'])),
           '--mount', f'type=bind,source={ROOT},target=/workspace', '-w', '/workspace/apps/backend',
           '-e', 'INTEGRATION_TEST_DATABASE_URL', '-e', 'PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/tmp/checkdeps',
           '-e', 'MODEL_CALLS_ENABLED=false', '-e', 'AUTHORING_PROVIDER=off', 'medresident-tutor-backend:latest', 'sh', '-c', script]
    result = subprocess.run(cmd, env={**os.environ, 'INTEGRATION_TEST_DATABASE_URL': url}, capture_output=True)
    output = (result.stdout + result.stderr).decode(errors='replace').replace(url, '[TEST_DATABASE]')
    (RUN / 'tests.log').write_text(output, encoding='utf-8')
    print(output[-6000:].encode('ascii', 'backslashreplace').decode())
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
