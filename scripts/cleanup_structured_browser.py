"""Remove only attempts recorded by this structured browser run; preserve all other rows."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
AUDIT = ROOT / "data/clinical-cases/exercises/structured/audit"
CODE = '''
import asyncio,json,uuid
import app.models
from sqlalchemy import select,delete
from sqlalchemy.engine import make_url
from app.core.config import get_settings
from app.core.database import SessionFactory,engine
from app.modules.practice.models import PracticeAttempt
from app.modules.questions.models import Question
from app.modules.users.models import User
async def main():
 cfg=get_settings();url=make_url(cfg.database_url)
 assert cfg.app_env=='development' and url.host=='db' and url.database=='medical_learning'
 removed=[]
 async with SessionFactory() as session,session.begin():
  for entry in owned:
   assert entry['question_id'] in {'CLINICAL_DEMO_V2_CASE01','CLINICAL_DEMO_V2_XR01'}
   user=await session.get(User,uuid.UUID(entry['user_id']))
   assert user and user.email in emails
   row=await session.scalar(select(PracticeAttempt).join(Question).where(
    PracticeAttempt.user_id==user.id,PracticeAttempt.idempotency_key==entry['key'],
    Question.external_id==entry['question_id']).with_for_update())
   if row is None: continue
   assert str(row.id) not in old_ids and row.execution_mode=='structured'
   removed.append(str(row.id))
   await session.delete(row)
 print(json.dumps({'removed_owned_test_attempts':removed,'preserved_other_data':True}))
 await engine.dispose()
asyncio.run(main())
'''


def main():
    owned = json.loads((AUDIT / "browser-owned-attempts.json").read_text())
    private = json.loads((ROOT / "data/backups/clinical-demo-accounts.json").read_text())
    location = json.loads((ROOT / "data/clinical-cases/exercises/backup-location.json").read_text())
    old = json.loads((ROOT / location["folder"] / "rows-before.json").read_bytes())
    context = {"owned": owned, "emails": [u["email"] for u in private["users"]],
               "old_ids": [r["id"] for r in old["practice_attempts"]]}
    script = "import json\ncontext=json.loads(" + repr(json.dumps(context)) + ")\nglobals().update(context)\n" + CODE
    result = subprocess.check_output([DOCKER, "exec", "-i", "medresident-tutor-backend-1",
                                      "python", "-"], input=script.encode())
    report = json.loads(result)
    (AUDIT / "browser-cleanup.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"owned_attempts_removed": len(report["removed_owned_test_attempts"])}))


if __name__ == "__main__":
    main()
