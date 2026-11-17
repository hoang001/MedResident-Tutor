"""Run browser checks with fixture backend; application DB is never used."""
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote
from .authoring_checks import DOCKER, ROOT, RUN


def main():
    inspected=json.loads(subprocess.check_output([DOCKER,"inspect","medresident-tutor-db-1"],text=True))[0]
    cfg=dict(e.split("=",1) for e in inspected["Config"]["Env"])
    network=next(iter(inspected["NetworkSettings"]["Networks"]))
    env={**os.environ,"DATABASE_URL":f"postgresql+asyncpg://{quote(cfg['POSTGRES_USER'])}:{quote(cfg['POSTGRES_PASSWORD'])}@db:5432/medresident_test_authoring_20261112"}
    name="medresident-authoring-browser"
    cmd=[DOCKER,"run","--rm","-d","--name",name,"--network",network,"--mount",f"type=bind,source={ROOT},target=/workspace","-w","/workspace",
         "-p","127.0.0.1:8104:8104","-e","DATABASE_URL","-e","PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/workspace",
         "-e","CORS_ORIGINS=http://host.docker.internal:3000","-e","PRACTICE_PROVIDER=mock","-e","MODEL_CALLS_ENABLED=false",
         "medresident-tutor-backend:latest","python","-m","uvicorn","local_model_testing.authoring_browser_app:app","--host","0.0.0.0","--port","8104","--no-access-log"]
    subprocess.run(cmd,env=env,check=True,capture_output=True)
    try:
        command=[DOCKER,"run","--rm","--mount",f"type=bind,source={ROOT},target=/workspace","-w","/workspace/apps/frontend",
             "mcr.microsoft.com/playwright:v1.56.1-noble","sh","-c","node node_modules/@playwright/test/cli.js test --config playwright.authoring.config.ts"]
        p=subprocess.run(command,capture_output=True)
        out=(p.stdout+p.stderr).decode("utf-8",errors="replace")
        (RUN/"browser.log").write_text(out,encoding="utf-8")
        print(out[-5000:].encode("ascii", "backslashreplace").decode())
        raise SystemExit(p.returncode)
    finally:
        subprocess.run([DOCKER,"stop",name],capture_output=True)


if __name__=="__main__":main()
