from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# __file__ — путь к текущему файлу app/config.py.
#
# resolve() превращает его в абсолютный путь.
# parent — директория app.
# parent.parent — корень проекта MLproject.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Конфигурация приложения.

    Значения сначала берутся из переменных окружения,
    затем из файла .env, а при их отсутствии используются
    значения по умолчанию.
    """

    model_config = SettingsConfigDict(
        # Файл с локальными переменными окружения.
        env_file=BASE_DIR / ".env",

        # Кодировка файла .env.
        env_file_encoding="utf-8",

        # DATABASE_URL и database_url считаются одним именем.
        case_sensitive=False,

        # Позволяет хранить в .env дополнительные переменные,
        # которые пока не описаны в Settings.
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Приложение
    # ------------------------------------------------------------------

    app_name: str = "Medical Learning Assistant"

    app_env: Literal["local", "test", "production"] = "local"

    debug: bool = True

    api_host: str = "127.0.0.1"

    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
    )

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    database_url: SecretStr

    database_pool_min_size: int = Field(
        default=1,
        ge=1,
        le=100,
    )

    database_pool_max_size: int = Field(
        default=10,
        ge=1,
        le=100,
    )

    database_command_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
    )

    # ------------------------------------------------------------------
    # Qdrant
    # ------------------------------------------------------------------

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "document_chunks_v1"

    embedding_model_name: str = "intfloat/multilingual-e5-large"
    embedding_dimension: int = 1024

    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 80

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    embedding_model_name: str = "intfloat/multilingual-e5-large"

    # dimension означает размерность вектора.
    # Для выбранной по умолчанию модели — 1024 компоненты.
    embedding_dimension: int = Field(
        default=1024,
        ge=1,
    )

    embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=512,
    )

    embedding_device: Literal[
        "auto",
        "cpu",
        "mps",
        "cuda",
    ] = "auto"

    normalize_embeddings: bool = True

    # ------------------------------------------------------------------
    # Разбиение документов на chunks
    # ------------------------------------------------------------------

    chunk_size_tokens: int = Field(
        default=800,
        ge=50,
        le=10_000,
    )

    chunk_overlap_tokens: int = Field(
        default=200,
        ge=0,
        le=5_000,
    )

    max_document_size_mb: int = Field(
        default=50,
        ge=1,
        le=1_000,
    )

    # ------------------------------------------------------------------
    # Поиск
    # ------------------------------------------------------------------

    retrieval_top_k: int = Field(
        default=20,
        ge=1,
        le=100,
    )

    minimum_retrieval_score: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )

    @field_validator("qdrant_url")
    @classmethod
    def normalize_qdrant_url(cls, value: str) -> str:
        """
        Удаляем завершающий слеш.

        Например:
            http://localhost:6333/
        превращается в:
            http://localhost:6333
        """

        normalized_value = value.rstrip("/")

        if not normalized_value.startswith(("http://", "https://")):
            raise ValueError(
                "qdrant_url должен начинаться с http:// или https://"
            )

        return normalized_value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """
        Позволяет написать в .env как INFO, так и info.
        """

        if isinstance(value, str):
            return value.upper()

        return value

    @model_validator(mode="after")
    def validate_chunking_settings(self) -> Settings:
        """
        Перекрытие должно быть меньше полного размера chunk.

        Иначе соседний chunk не будет нормально продвигаться
        по документу.
        """

        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError(
                "chunk_overlap_tokens должен быть меньше "
                "chunk_size_tokens"
            )

        return self

    @model_validator(mode="after")
    def validate_database_pool(self) -> Settings:
        """
        Минимальный размер пула соединений не может быть
        больше максимального.
        """

        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError(
                "database_pool_min_size не может быть больше "
                "database_pool_max_size"
            )

        return self

    def get_database_url(self) -> str:
        """
        Возвращает настоящий DATABASE_URL.

        SecretStr специально скрывает секрет при обычном print.
        Для передачи строки драйверу PostgreSQL вызываем
        get_secret_value().
        """

        return self.database_url.get_secret_value()

    def get_qdrant_api_key(self) -> str | None:
        """Возвращает настоящий API-ключ Qdrant, если он задан."""

        if self.qdrant_api_key is None:
            return None

        return self.qdrant_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """
    Создаёт и кеширует объект конфигурации.

    lru означает least recently used — наименее недавно
    использованный.

    Здесь декоратор используется не как обычный LRU-кеш
    множества значений: функция не принимает аргументов,
    поэтому Settings создаётся один раз за время работы процесса.
    """

    return Settings()


settings = get_settings()