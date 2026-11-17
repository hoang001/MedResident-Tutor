import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


def shared_api_key_variable():
    """One service key; an explicit MODEL key wins, including invalid placeholders."""
    if os.environ.get("MODEL_SERVICE_API_KEY") or not os.environ.get("MEDICAL_API_KEY"):
        return "MODEL_SERVICE_API_KEY"
    return "MEDICAL_API_KEY"


@dataclass(frozen=True)
class Settings:
    env_prefix: ClassVar[str] = "MEDICAL"
    base_path: Path
    adapter_path: Path
    adapter_sha256: str
    base_config_sha256: str
    api_key: str = field(repr=False)
    adapter_config_sha256: str
    max_body_bytes: int = 262144
    max_input_tokens: int = 4096
    max_context_tokens: int = 8192

    def __post_init__(self):
        if not self.base_path.is_absolute() or not self.adapter_path.is_absolute():
            raise ValueError("Base model and adapter paths must be absolute local directories")
        if len(self.api_key.strip()) < 16 or any(c in self.api_key for c in "<>\r\n"):
            raise ValueError(
                "Model service API key must contain at least 16 non-placeholder characters"
            )
        for name, value in (
            (self.env_prefix + "_ADAPTER_SHA256", self.adapter_sha256),
            (self.env_prefix + "_BASE_CONFIG_SHA256", self.base_config_sha256),
            (self.env_prefix + "_ADAPTER_CONFIG_SHA256", self.adapter_config_sha256),
        ):
            if not re.fullmatch("[0-9a-f]{64}", value):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if min(self.max_body_bytes, self.max_input_tokens, self.max_context_tokens) <= 0:
            raise ValueError("Input/context limits must be positive")

    @classmethod
    def from_env(cls, *, api_key_variable=None):
        if os.getenv("WEB_CONCURRENCY", "1") != "1":
            raise ValueError("Medical MVP requires WEB_CONCURRENCY=1")
        prefix = cls.env_prefix
        names = (
            prefix + "_BASE_MODEL_PATH",
            prefix + "_ADAPTER_PATH",
            prefix + "_ADAPTER_SHA256",
            prefix + "_BASE_CONFIG_SHA256",
            api_key_variable or prefix + "_API_KEY",
            prefix + "_ADAPTER_CONFIG_SHA256",
        )
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            raise ValueError("Missing environment variables: " + ", ".join(missing))
        return cls(
            base_path=Path(os.environ[names[0]]),
            adapter_path=Path(os.environ[names[1]]),
            adapter_sha256=os.environ[names[2]],
            base_config_sha256=os.environ[names[3]],
            api_key=os.environ[names[4]],
            adapter_config_sha256=os.environ[names[5]],
            max_body_bytes=int(os.getenv(prefix + "_MAX_BODY_BYTES", "262144")),
            max_input_tokens=int(os.getenv(prefix + "_MAX_INPUT_TOKENS", "4096")),
            max_context_tokens=int(os.getenv(prefix + "_MAX_CONTEXT_TOKENS", "8192")),
        )


class TeachingSettings(Settings):
    env_prefix = "TEACHING"
