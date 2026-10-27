import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
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
        if len(self.api_key) < 16:
            raise ValueError("MEDICAL_API_KEY must contain at least 16 characters")
        for name, value in (
            ("MEDICAL_ADAPTER_SHA256", self.adapter_sha256),
            ("MEDICAL_BASE_CONFIG_SHA256", self.base_config_sha256),
            ("MEDICAL_ADAPTER_CONFIG_SHA256", self.adapter_config_sha256),
        ):
            if not re.fullmatch("[0-9a-f]{64}", value):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if min(self.max_body_bytes, self.max_input_tokens, self.max_context_tokens) <= 0:
            raise ValueError("Input/context limits must be positive")

    @classmethod
    def from_env(cls):
        if os.getenv("WEB_CONCURRENCY", "1") != "1":
            raise ValueError("Medical MVP requires WEB_CONCURRENCY=1")
        names = (
            "MEDICAL_BASE_MODEL_PATH",
            "MEDICAL_ADAPTER_PATH",
            "MEDICAL_ADAPTER_SHA256",
            "MEDICAL_BASE_CONFIG_SHA256",
            "MEDICAL_API_KEY",
            "MEDICAL_ADAPTER_CONFIG_SHA256",
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
            max_body_bytes=int(os.getenv("MEDICAL_MAX_BODY_BYTES", "262144")),
            max_input_tokens=int(os.getenv("MEDICAL_MAX_INPUT_TOKENS", "4096")),
            max_context_tokens=int(os.getenv("MEDICAL_MAX_CONTEXT_TOKENS", "8192")),
        )
