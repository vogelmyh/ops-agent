from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_mode: Literal["mock", "real"] = "mock"
    backend_base_url: str = "http://localhost:8080"
    llm_mode: Literal["mock", "real"] = "mock"
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_model_strong: str = "gpt-4o"
    embeddings_provider: Literal["local-hash", "openai", "qwen", "bge"] = "local-hash"
    embeddings_model: str = "text-embedding-v4"
    qwen_api_key: str | None = Field(default=None, validation_alias="QWEN_API_KEY")
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    checkpointer: Literal["sqlite", "memory", "redis"] = "sqlite"
    checkpointer_sqlite_path: str = "./data/checkpoints.db"
    redis_url: str = "redis://localhost:6379/0"
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"),
    )
    langsmith_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    langsmith_project: str = Field(
        default="ops-agent",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
    )
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    max_remediation_attempts: int = 3
    retrieval_hybrid_top_k: int = 20
    retrieval_rerank_chunk_top_k: int = 10
    retrieval_final_top_k: int = 3
    retrieval_rrf_k: int = 60
    retrieval_rerank_min_score: float = 0.15
    runbook_relevance_threshold: float = 0.55
    runbook_coverage_threshold: float = 0.70
    runbook_disambiguation_gap: float = 0.12
    runbook_disambiguation_top1_cap: float = 0.75
    diagnosis_confidence_threshold: float = 0.55

    @property
    def backend_is_mock(self) -> bool:
        return self.backend_mode == "mock"

    @property
    def llm_is_mock(self) -> bool:
        return self.llm_mode == "mock"

    @property
    def langsmith_enabled(self) -> bool:
        return self.langsmith_tracing and bool(self.langsmith_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
