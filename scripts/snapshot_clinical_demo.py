"""Back up the explicitly named local Compose database without exposing credentials."""
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
DB = "medresident-tutor-db-1"
BACKEND = "medresident-tutor-backend-1"
ROW_SCRIPT = '''
import asyncio,json,re
from sqlalchemy import text
from app.core.database import engine
from app.core.config import get_settings
from sqlalchemy.engine import make_url
async def run():
 c=get_settings();u=make_url(c.database_url)
 assert c.app_env=='development' and u.host=='db' and u.database=='medical_learning'
 result={}
 async with engine.connect() as conn:
  names=(await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all()
  for name in sorted(names):
   assert re.fullmatch('[a-z_0-9]+',name)
   rows=(await conn.execute(text('SELECT row_to_json(t)::text FROM "'+name+'" t'))).scalars().all()
   result[name]=[json.loads(row) for row in rows]
 print(json.dumps(result,ensure_ascii=False,sort_keys=True))
 await engine.dispose()
asyncio.run(run())
'''


def main():
    inspect = json.loads(subprocess.check_output([DOCKER, "inspect", DB]))[0]
    assert inspect["Config"]["Labels"]["com.docker.compose.project"] == "medresident-tutor"
    assert inspect["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] == "127.0.0.1"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "data/backups" / ("clinical-exercise-demo-" + stamp)
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / "postgres.dump").open("wb") as stream:
        subprocess.run([DOCKER, "exec", DB, "sh", "-c", 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'], stdout=stream, check=True)
    result = subprocess.check_output([DOCKER, "exec", "-i", BACKEND, "python", "-"], input=ROW_SCRIPT.encode())
    (folder / "rows-before.json").write_bytes(result)
    hashes = {}
    for root in (ROOT / "model-training", ROOT / "data/processed", ROOT / "data/integration"):
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".json", ".jsonl", ".txt", ".yaml"} and not any(part in {"outputs", "checkpoints", "logs", "__pycache__"} for part in p.parts):
                hashes[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    (folder / "protected-file-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    (ROOT / "data/clinical-cases/exercises/backup-location.json").write_text(json.dumps({"folder": folder.relative_to(ROOT).as_posix()}), encoding="utf-8")
    rows = json.loads(result)
    print(json.dumps({"backup": folder.relative_to(ROOT).as_posix(), "tables": len(rows), "existing_rows": sum(len(v) for v in rows.values()), "protected_files": len(hashes)}))


if __name__ == "__main__":
    main()
