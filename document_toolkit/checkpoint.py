"""General-purpose checkpoint and JSON-response cache; no skills/IXL ID assumptions."""
from copy import deepcopy
from pathlib import Path

from .common import fingerprint,read_json,write_json,validate_schema


class Checkpoint:
    def __init__(self,path,signature,*,resume=False,force=False):
        if resume and force:raise ValueError('Choose resume or force, not both')
        self.path=Path(path)
        if resume:
            if not self.path.exists():raise ValueError('No checkpoint found; start without --continue')
            self.data=read_json(self.path)
            if self.data.get('fingerprint')!=signature:
                raise ValueError('Input/prompt/schema/config/code changed. Use another output or --force to restart.')
        else:
            if self.path.exists() and not force:raise ValueError('Checkpoint exists; use --continue or another output')
            self.data={'fingerprint':signature,'calls':{},'position':{},'complete':False}
            self.save()
    def save(self):write_json(self.path,self.data)


class CachedLLM:
    def __init__(self,client,checkpoint,*,namespace=''):
        self.client,self.checkpoint,self.namespace=client,checkpoint,namespace

    def chat_json(self,model,messages,schema=None,*,validator=None):
        key=fingerprint([self.namespace,model,messages,schema])
        calls=self.checkpoint.data['calls']
        if key in calls:
            result=deepcopy(calls[key])
            if schema is not None:validate_schema(result,schema)
            if validator is not None:validator(result)
            return result
        result=self.client.chat_json(model,messages,schema)
        if schema is not None:validate_schema(result,schema)
        if validator is not None:validator(result)
        calls[key]=deepcopy(result);self.checkpoint.save()
        return result
