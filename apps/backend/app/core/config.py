from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Medical Resident Learning Assistant"
    seed_admin_email: str = ""
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://medical_user:local_development_password@localhost:5432/medical_learning"
    jwt_secret_key: str = Field(default="local-development-only-secret-change-me", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)
    cors_origins: list[str] | str = ["http://localhost:3000"]
    file_storage_path: Path = Path("data/uploads")
    max_upload_size_mb: int = Field(default=10, gt=0)
    llm_provider: str = "mock"
    model_calls_enabled: bool = False
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = Field(default="", repr=False)
    neo4j_database: str = "neo4j"
    knowledge_data_root: Path = Path("data")
    knowledge_cache_seconds: float = Field(default=20, ge=0, le=300)
    practice_provider: str = "mock"
    runpod_pod_id: str = ""
    model_service_base_url: str = ""
    model_service_api_key: str = Field(default="", repr=False)
    model_service_connect_timeout_seconds: float = Field(default=10, gt=0, le=60)
    model_service_read_timeout_seconds: float = Field(default=120, gt=0, le=1800)
    authoring_provider: Literal["off", "local_http", "service_http", "openai", "runpod"] = "off"
    authoring_service_url: str = "http://host.docker.internal:8103"
    authoring_service_api_key: str = Field(default="", repr=False)
    authoring_model: str = ""
    practice_mock_scenario: str = "success"
    practice_retrieval_strategy: Literal["prelinked", "vector", "kg_lookup", "hybrid"] = "prelinked"
    practice_retrieval_graph: Literal["neo4j", "offline"] = "neo4j"
    practice_retrieval_corpus: Path = Path("data/retrieval/book-corpus-v1")
    practice_retrieval_encoder: Path = Path("data/local-models/embeddings/multilingual-e5-small")
    practice_retrieval_mapping: Path = (
        Path(__file__).resolve().parents[1] / "ai/retrieval/book_mapping.v1.json"
    )
    practice_retrieval_snapshot: Path = Path(
        "data/evaluation/medresident-benchmark-v1/graph-snapshot.json"
    )
    practice_retrieval_min_similarity: float = Field(default=0.75, ge=0, le=1)
    practice_timeout_seconds: float = Field(default=30, gt=0, le=300)
    practice_runtime_profile: Literal["default", "local"] = "default"
    practice_local_medical_read_seconds: float = Field(default=90, gt=0, le=600)
    practice_local_connect_seconds: float = Field(default=5, gt=0, le=30)
    practice_local_write_seconds: float = Field(default=10, gt=0, le=60)
    practice_local_pool_seconds: float = Field(default=5, gt=0, le=30)
    practice_local_deadline_grace_seconds: float = Field(default=5, gt=0, le=60)
    medical_service_url: str = ""
    teaching_service_url: str = ""
    medical_service_api_key: str = Field(default="", repr=False)
    teaching_service_api_key: str = Field(default="", repr=False)
    medical_api_format: Literal["service", "openai"] = "service"
    teaching_api_format: Literal["service", "openai"] = "service"
    medical_model: str = ""
    teaching_model: str = ""
    embedding_provider: str = "mock"
    google_client_id: str = ""

    @model_validator(mode="after")
    def local_practice_is_development_only(self):
        if self.practice_runtime_profile == "local" and self.app_env != "development":
            raise ValueError("Local practice timeout profile requires development")
        return self

    def practice_transport_timeouts(self, stage: str) -> dict[str, float]:
        if stage not in {"medical", "teaching"}:
            raise ValueError("Unknown practice stage")
        if self.practice_provider == "runpod":
            return dict(
                connect=self.model_service_connect_timeout_seconds,
                read=self.model_service_read_timeout_seconds,
                write=10,
                pool=5,
            )
        if self.practice_runtime_profile == "local" and stage == "medical":
            return dict(
                connect=self.practice_local_connect_seconds,
                read=self.practice_local_medical_read_seconds,
                write=self.practice_local_write_seconds,
                pool=self.practice_local_pool_seconds,
            )
        return dict.fromkeys(("connect", "read", "write", "pool"), self.practice_timeout_seconds)

    def practice_stage_deadline(self, stage: str) -> float:
        if self.practice_provider == "runpod":
            return sum(self.practice_transport_timeouts(stage).values()) + 5
        if self.practice_runtime_profile == "local" and stage == "medical":
            return (
                sum(self.practice_transport_timeouts(stage).values())
                + self.practice_local_deadline_grace_seconds
            )
        return self.practice_timeout_seconds

    def practice_request_timeout_ms(self) -> int:
        # Covers both sequential stages plus auth/DB/response/browser overhead.
        return int(
            (
                self.practice_stage_deadline("medical")
                + self.practice_stage_deadline("teaching")
                + 10
            )
            * 1000
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
