"""UTF-8 JSON, atomic writes, content fingerprints and schema validation."""
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from jsonschema import Draft202012Validator


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        for attempt in range(10):
            try:temporary.replace(path);break
            except PermissionError:
                if attempt==9:raise
                time.sleep(min(.2*(attempt+1),1))
    finally:
        if temporary.exists():temporary.unlink()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def validate_schema(value,schema):
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)
