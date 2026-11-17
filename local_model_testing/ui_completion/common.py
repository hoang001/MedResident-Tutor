import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'data/authoring/ui-completion-20261116'
DOCKER='C:/Program Files/Docker/Docker/resources/bin/docker.exe'
RUN.mkdir(parents=True,exist_ok=True)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(name,value):
    p=RUN/name; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def read(name): return json.loads((RUN/name).read_text(encoding='utf-8'))

def inside(module,*args):
    info=json.loads(subprocess.check_output([DOCKER,'inspect','medresident-tutor-backend-1']))[0]
    env=dict(e.split('=',1) for e in info['Config']['Env'])
    env.update(PYTHONPATH='/workspace:/workspace/apps/backend:/workspace/model-training',KNOWLEDGE_DATA_ROOT='/workspace/data',MODEL_CALLS_ENABLED='false',AUTHORING_PROVIDER='off')
    cmd=[DOCKER,'run','--rm','--name','medresident-ui-data-check','--network',next(iter(info['NetworkSettings']['Networks'])),
         '--mount',f'type=bind,source={ROOT},target=/workspace','-w','/workspace']
    for key in env: cmd+=['-e',key]
    cmd+=['medresident-tutor-backend:latest','python','-m','local_model_testing.ui_completion.'+module,'--inside',*args]
    p=subprocess.run(cmd,env={**os.environ,**env},capture_output=True)
    out=(p.stdout+p.stderr).decode(errors='replace')
    for k,v in env.items():
        if v and any(w in k for w in ('KEY','SECRET','PASSWORD','URL')): out=out.replace(v,'[REDACTED]')
    (RUN/(module+'.log')).write_text(out,encoding='utf-8')
    print(out[-4000:].encode('ascii','backslashreplace').decode())
    if p.returncode: raise SystemExit(p.returncode)
