"""Standalone LLM settings; no Neo4j, grade or company-specific defaults."""
from dataclasses import dataclass,field
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv


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
    def from_env(cls,env_file='.env'):
        load_dotenv(env_file,override=False)
        return cls(llm_base_url=os.getenv('LLM_BASE_URL') or os.getenv('OPENAI_BASE_URL',''),
                   llm_api_key=os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY',''),
                   model=os.getenv('LLM_MODEL',''),judge_model=os.getenv('LLM_JUDGE_MODEL',''),
                   llm_chat_completions_endpoint=os.getenv('LLM_CHAT_ENDPOINT','/v1/chat/completions'),
                   llm_timeout_seconds=float(os.getenv('LLM_TIMEOUT_SECONDS','120')),
                   llm_max_attempts=int(os.getenv('LLM_MAX_ATTEMPTS','3')),
                   prompt_budget_bytes=int(os.getenv('LLM_PROMPT_BUDGET_BYTES','30000')),
                   max_output_tokens=int(os.getenv('LLM_MAX_OUTPUT_TOKENS','4096')))
