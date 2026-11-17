"""Standalone LLM settings; no Neo4j, grade or company-specific defaults."""
from dataclasses import dataclass,field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / '.env'


@dataclass(frozen=True)
class Settings:
    llm_base_url:str=''
    llm_api_key:str=field(default='',repr=False)
    model:str=''
    judge_model:str=''
    llm_chat_completions_endpoint:str='/v1/chat/completions'
    llm_timeout_seconds:float=120
    llm_max_attempts:int=3
    prompt_budget_bytes:int=30000
    max_output_tokens:int=4096

    def __post_init__(self):
        if self.llm_timeout_seconds<=0 or self.llm_max_attempts<1 or self.prompt_budget_bytes<1 or self.max_output_tokens<1:
            raise ValueError('Timeout, attempts, prompt budget and max output tokens must be positive')

    def endpoint_url(self,endpoint):
        base=self.llm_base_url.rstrip('/');suffix='/'+endpoint.lstrip('/')
        if urlsplit(base).path.rstrip('/').endswith('/v1') and suffix.startswith('/v1/'):
            suffix=suffix[3:]
        return base+suffix

    @classmethod
    def from_env(cls,env_file=DEFAULT_ENV_FILE):
        path = Path(env_file)
        if not path.is_file():
            raise ValueError('ENV_FILE_NOT_FOUND')
        values = dotenv_values(path, interpolate=False)
        def get(name, default=''):
            return values.get(name) or default
        return cls(llm_base_url=get('LLM_BASE_URL').strip(),
                   llm_api_key=get('LLM_API_KEY').strip(),
                   model=get('LLM_MODEL'),judge_model=get('LLM_JUDGE_MODEL'),
                   llm_chat_completions_endpoint=get('LLM_CHAT_ENDPOINT','/v1/chat/completions'),
                   llm_timeout_seconds=float(get('LLM_TIMEOUT_SECONDS','120')),
                   llm_max_attempts=int(get('LLM_MAX_ATTEMPTS','3')),
                   prompt_budget_bytes=int(get('LLM_PROMPT_BUDGET_BYTES','30000')),
                   max_output_tokens=int(get('LLM_MAX_OUTPUT_TOKENS','4096')))
