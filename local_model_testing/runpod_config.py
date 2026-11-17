"""Show effective Compose model configuration without keys or network/model calls."""
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
DOCKER="C:/Program Files/Docker/Docker/resources/bin/docker.exe"


def filled(value):
    return bool(value and value.strip() and '<' not in value and '>' not in value)


def main():
    cmd=[DOCKER,'compose','--env-file',str(ROOT/'.env'),'-f','docker-compose.yml',
        '-f','docker-compose.authoring.yml','config','--format','json']
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True)
    if p.returncode:
        raise SystemExit('Compose configuration could not be resolved; no values printed')
    env=json.loads(p.stdout)['services']['backend']['environment']
    report={'env_file':str(ROOT/'.env'),'network_requests':0,
        'model_calls_enabled':str(env.get('MODEL_CALLS_ENABLED','false')).lower()=='true',
        'practice_provider':env.get('PRACTICE_PROVIDER','mock'),
        'authoring_provider':env.get('AUTHORING_PROVIDER','off'),'models':{},'terminal_overrides':[]}
    for stage in ('MEDICAL','TEACHING','AUTHORING'):
        base=env.get(stage+'_SERVICE_URL','')
        parts=urlsplit(base)
        safe_url=base if not(parts.username or parts.password or parts.query or parts.fragment) else '[URL_REDACTED_INVALID]'
        report['models'][stage.lower()]={'base_url':safe_url,'model':env.get(stage+'_MODEL',''),
            'key_filled':filled(env.get(stage+'_SERVICE_API_KEY','')),
            'url_filled':filled(base),'api_format':env.get(stage+'_API_FORMAT',report['authoring_provider'])}
    names=['MODEL_CALLS_ENABLED','PRACTICE_PROVIDER','AUTHORING_PROVIDER']
    names += [s+suffix for s in ('MEDICAL','TEACHING','AUTHORING') for suffix in ('_SERVICE_URL','_SERVICE_API_KEY','_MODEL','_API_FORMAT')]
    report['terminal_overrides']=[key for key in names if key in os.environ]
    path=ROOT/'data/authoring/runpod-config-20261112/effective-config.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
