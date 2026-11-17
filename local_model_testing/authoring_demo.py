"""Create two unissued source-excerpt drafts, with actual CPU retrieval and no LLM."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path


async def inside():
    import app.models  # noqa: F401
    from sqlalchemy import select
    from app.core.database import SessionFactory
    from app.common.enums import UserRole
    from app.modules.questions import authoring
    from app.modules.questions.models import Question
    from app.modules.questions.schemas import QuestionEdit
    from app.modules.questions.service import save
    from app.modules.users.models import User
    path=Path("/workspace/data/authoring/checks-20261112")
    results=[]
    async with SessionFactory() as session:
        admin=await session.scalar(select(User).where(User.role==UserRole.ADMIN,User.is_active.is_(True)))
        if not admin:
            raise RuntimeError("No existing active administrator; not creating or promoting accounts")
        admin_id=admin.id
    catalog=json.loads(Path("/workspace/data/retrieval/book-corpus-v1/catalog.json").read_text(encoding="utf-8"))
    queries=["Trình bày nguyên tắc xử trí vết thương phần mềm.","Trình bày dấu hiệu và chẩn đoán gãy đầu dưới xương quay."]
    for book,query in zip(catalog["books"][:2],queries,strict=True):
        scope=authoring.Scope(question=query,topic=query,source_ids=[book["id"]])
        bundle=await authoring.retrieve(scope)
        results.append({"scope":scope.model_dump(),"retrieval":bundle["trace"],"evidence":bundle["evidence"],"mode":"manual_source_excerpt_no_llm"})
        if not bundle["evidence"]:
            continue
        selection=authoring.Selection(bundle_token=bundle["bundle_token"],selected_ids=[bundle["evidence"][0]["source_unit_id"]])
        async with SessionFactory() as session,session.begin():
            rows=await authoring.materialize(session,admin_id,selection)
            content="[Nháp minh họa nguồn — chưa duyệt] "+query
            existing=await session.scalar(select(Question).where(Question.content==content))
            if existing:
                results[-1]["question_id"]=existing.external_id
                continue
            body=QuestionEdit(content=content,rubric_name="Bản nháp cần admin biên soạn",max_score=1,
                topic=query,reference_answer="TRÍCH NGUỒN ĐỂ ADMIN BIÊN SOẠN, CHƯA PHẢI ĐÁP ÁN ĐÃ DUYỆT:\n"+rows[0]["content"],
                criteria=[{"description":"Trình bày nội dung được đoạn nguồn hỗ trợ, giữ điều kiện và ngoại lệ. Admin cần cụ thể hóa tiêu chí trước khi phát hành.",
                    "max_score":1,"source_unit_ids":[rows[0]["source_unit_id"]]}])
            result=await save(session,admin_id,body)
            assert not result["is_available"]
            results[-1]["question_id"]=result["question_id"]
    path.mkdir(parents=True,exist_ok=True)
    (path/"demo-drafts.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"drafts":sum("question_id" in r for r in results),"llm_calls":0,"retrievals":len(results)}))


def main():
    if "--inside" in sys.argv:
        return asyncio.run(inside())
    from .authoring_checks import ROOT,DOCKER
    inspected=json.loads(subprocess.check_output([DOCKER,"inspect","medresident-tutor-backend-1"],text=True))[0]
    env=dict(e.split("=",1) for e in inspected["Config"]["Env"])
    env["PYTHONPATH"]="/workspace/apps/backend:/workspace/model-training:/usr/local/lib/python3.12/site-packages"
    network=next(iter(inspected["NetworkSettings"]["Networks"]))
    cmd=[DOCKER,"run","--rm","--name","medresident-authoring-demo","--network",network,
         "--mount",f"type=bind,source={ROOT},target=/workspace","--mount","type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv","-w","/workspace"]
    for key in env:cmd.extend(["-e",key])
    cmd += ["--entrypoint","/opt/local-models-venv/bin/python","medresident-tutor-backend:latest","-m","local_model_testing.authoring_demo","--inside"]
    result=subprocess.run(cmd,env={**os.environ,**env},capture_output=True)
    out=(result.stdout+result.stderr).decode("utf-8",errors="replace")
    for key,value in env.items():
        if value and any(k in key for k in ("PASSWORD","SECRET","KEY","URL")):out=out.replace(value,"[REDACTED]")
    (ROOT/"data/authoring/checks-20261112/demo.log").write_text(out,encoding="utf-8")
    print(out[-2500:].encode("ascii","backslashreplace").decode())
    raise SystemExit(result.returncode)


if __name__=="__main__":main()
