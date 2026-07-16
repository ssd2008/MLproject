from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Medical Learning Assistant"
    app_version: str = "0.3.0"
    app_env: Literal["local", "test", "production"] = "local"
    debug: bool = False
    api_prefix: str = "/api/v1"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    database_url: SecretStr = SecretStr(
        "postgresql://med_user:med_pass@localhost:5432/med_assistant"
    )
    database_pool_min_size: int = Field(default=1, ge=1, le=50)
    database_pool_max_size: int = Field(default=10, ge=1, le=100)
    database_command_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection_name: str = "document_chunks_v1"
    qdrant_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    qdrant_upsert_batch_size: int = Field(default=64, ge=1, le=1000)

    embedding_backend: Literal["hash", "sentence-transformers"] = "hash"
    embedding_model_name: str = "intfloat/multilingual-e5-large"
    embedding_dimension: int = Field(default=1024, ge=8, le=16384)
    embedding_batch_size: int = Field(default=16, ge=1, le=512)
    embedding_device: Literal["auto", "cpu", "mps", "cuda"] = "auto"
    normalize_embeddings: bool = True

    reranker_backend: Literal["lexical", "cross-encoder"] = "lexical"
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_batch_size: int = Field(default=16, ge=1, le=256)
    reranker_device: Literal["auto", "cpu", "mps", "cuda"] = "auto"

    answer_backend: Literal["extractive", "openai"] = "extractive"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"

    asr_backend: Literal["disabled", "faster-whisper"] = "faster-whisper"
    asr_model_name: str = "small"
    asr_device: Literal["auto", "cpu", "cuda"] = "cpu"
    asr_compute_type: Literal["int8", "float16", "float32", "int8_float16"] = "int8"
    asr_beam_size: int = Field(default=5, ge=1, le=20)
    asr_vad_filter: bool = True

    chunk_size_tokens: int = Field(default=400, ge=50, le=5000)
    chunk_overlap_tokens: int = Field(default=80, ge=0, le=2000)
    video_chunk_duration_seconds: float = Field(default=10.0, ge=3.0, le=120.0)
    video_chunk_overlap_seconds: float = Field(default=2.0, ge=0.0, le=30.0)
    retrieval_top_k: int = Field(default=10, ge=1, le=100)
    retrieval_candidate_k: int = Field(default=30, ge=1, le=300)
    minimum_retrieval_score: float | None = Field(default=None, ge=-1.0, le=1.0)

    max_document_size_mb: int = Field(default=10, ge=1, le=500)
    max_video_size_mb: int = Field(default=500, ge=1, le=5000)
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    url_fetch_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    url_fetch_max_redirects: int = Field(default=5, ge=0, le=20)
    url_user_agent: str = "MedicalLearningAssistant/0.3"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("qdrant_url")
    @classmethod
    def normalize_qdrant_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("qdrant_url must start with http:// or https://")
        return value

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = "/" + value.strip("/")
        return "" if value == "/" else value

    @model_validator(mode="after")
    def validate_related_values(self) -> "Settings":
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("database_pool_min_size cannot exceed database_pool_max_size")
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
        if self.video_chunk_overlap_seconds >= self.video_chunk_duration_seconds:
            raise ValueError(
                "video_chunk_overlap_seconds must be smaller than video_chunk_duration_seconds"
            )
        if self.retrieval_candidate_k < self.retrieval_top_k:
            raise ValueError("retrieval_candidate_k cannot be smaller than retrieval_top_k")
        if self.answer_backend == "openai" and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when ANSWER_BACKEND=openai")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def max_document_size_bytes(self) -> int:
        return self.max_document_size_mb * 1024 * 1024

    @property
    def max_video_size_bytes(self) -> int:
        return self.max_video_size_mb * 1024 * 1024

    def get_database_url(self) -> str:
        return self.database_url.get_secret_value()

    def get_qdrant_api_key(self) -> str | None:
        return self.qdrant_api_key.get_secret_value() if self.qdrant_api_key else None

    def get_openai_api_key(self) -> str | None:
        return self.openai_api_key.get_secret_value() if self.openai_api_key else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
