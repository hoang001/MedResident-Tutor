"""Run scoped checks against a separate PostgreSQL DB; never reset the application DB."""
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
DOCKER="C:/Program Files/Docker/Docker/resources/bin/docker.exe"
RUN=ROOT/"data/authoring/checks-20261112"


def main():
    RUN.mkdir(parents=True,exist_ok=True)
    inspected=json.loads(subprocess.check_output([DOCKER,"inspect","medresident-tutor-db-1"],text=True))[0]
    config=dict(e.split("=",1) for e in inspected["Config"]["Env"])
    network=next(iter(inspected["NetworkSettings"]["Networks"]))
    database="medresident_test_authoring_20261112"
    subprocess.run([DOCKER,"exec","medresident-tutor-db-1","createdb","-U",config["POSTGRES_USER"],database],capture_output=True)
    url=f"postgresql+asyncpg://{quote(config['POSTGRES_USER'])}:{quote(config['POSTGRES_PASSWORD'])}@db:5432/{database}"
    env={**os.environ,"INTEGRATION_TEST_DATABASE_URL":url}
    cmd=[DOCKER,"run","--rm","--network",network,"--mount",f"type=bind,source={ROOT},target=/workspace","-w","/workspace/apps/backend",
         "-e","INTEGRATION_TEST_DATABASE_URL","-e","PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/tmp/checkdeps",
         "medresident-tutor-backend:latest","sh","-c",
         "pip install -q --target /tmp/checkdeps pytest pytest-asyncio ruff aiosqlite numpy && PYTHONPATH=/tmp/checkdeps python -m ruff format app/modules/questions app/modules/practice/service.py tests/test_authoring.py postgres_tests/test_authoring_workflow.py && PYTHONPATH=/tmp/checkdeps python -m ruff check app/modules/questions app/modules/practice/service.py tests/test_authoring.py postgres_tests/test_authoring_workflow.py --fix && python -m pytest -q tests/test_authoring.py tests/test_practice_contracts.py tests/test_practice_retrieval.py tests/test_structured_practice.py postgres_tests/test_authoring_workflow.py postgres_tests/test_question_bank.py --junitxml=/workspace/data/authoring/checks-20261112/results.xml"]
    result=subprocess.run(cmd,env=env,capture_output=True)
    out=(result.stdout+result.stderr).decode("utf-8",errors="replace").replace(url,"[DATABASE]")
    (RUN/"tests.log").write_text(out,encoding="utf-8")
    print(out[-7000:])
    raise SystemExit(result.returncode)


if __name__=="__main__": main()
