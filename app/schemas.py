from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class APIModel(BaseModel):
    """
    Общая базовая модель для всех схем API.

    Все остальные схемы наследуются от неё, чтобы не повторять
    общие настройки Pydantic.
    """

    model_config = ConfigDict(
        # Запрещаем неизвестные поля.
        # Например, "topkk" вместо "top_k" вызовет ошибку,
        # а не будет молча проигнорировано.
        extra="forbid",

        # Автоматически убираем пробелы в начале и конце строк.
        str_strip_whitespace=True,

        # Разрешаем создавать схемы из объектов репозитория/ORM,
        # а не только из обычных словарей.
        from_attributes=True,
    )


class SourceType(StrEnum):
    """
    Тип источника документа.

    StrEnum означает string enum — строковое перечисление.
    В JSON значения будут представлены обычными строками.
    """

    PDF = "pdf"
    URL = "url"
    TEXT = "text"


class DocumentStatus(StrEnum):
    """Текущее состояние обработки документа."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentIn(APIModel):
    """
    Данные, необходимые для создания документа.

    Для PDF сам файл будет передаваться endpoint-у отдельно
    через FastAPI UploadFile. Здесь хранятся его метаданные.
    """

    title: str = Field(
        min_length=1,
        max_length=300,
        description="Название документа",
    )

    source_type: SourceType

    # Используется только для source_type="url".
    source_url: HttpUrl | None = None

    # Используется только для source_type="text".
    raw_text: str | None = Field(
        default=None,
        min_length=1,
        description="Текст документа, переданный напрямую",
    )

    specialty: str | None = Field(
        default=None,
        max_length=100,
        description="Медицинская специальность",
    )

    lecture_date: date | None = Field(
        default=None,
        description="Дата лекции или материала",
    )

    # Дополнительные данные, которые заранее предусмотреть невозможно.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_payload(self) -> DocumentIn:
        """
        Проверяем соответствие source_type и содержимого документа.

        mode="after" означает, что валидатор запускается после того,
        как Pydantic уже проверил отдельные поля.
        """

        if self.source_type == SourceType.URL and self.source_url is None:
            raise ValueError(
                "Для source_type='url' необходимо указать source_url"
            )

        if self.source_type == SourceType.TEXT and not self.raw_text:
            raise ValueError(
                "Для source_type='text' необходимо указать raw_text"
            )

        if self.source_type != SourceType.URL and self.source_url is not None:
            raise ValueError(
                "source_url разрешён только для source_type='url'"
            )

        if self.source_type != SourceType.TEXT and self.raw_text is not None:
            raise ValueError(
                "raw_text разрешён только для source_type='text'"
            )

        return self


class DocumentOut(APIModel):
    """Документ, возвращаемый клиенту через API."""

    id: UUID
    title: str
    source_type: SourceType
    status: DocumentStatus

    source_url: HttpUrl | None = None
    specialty: str | None = None
    lecture_date: date | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Количество фрагментов документа",
    )

    error_message: str | None = None

    created_at: datetime
    updated_at: datetime


class Chunk(APIModel):
    """
    Фрагмент документа.

    Chunk означает фрагмент или кусок. Документ разбивается
    на такие фрагменты перед созданием embeddings.
    """

    id: UUID
    document_id: UUID

    # Порядковый номер фрагмента внутри документа.
    chunk_index: int = Field(ge=0)

    text: str = Field(min_length=1)

    token_count: int = Field(
        ge=1,
        description="Количество токенов во фрагменте",
    )

    page_number: int | None = Field(
        default=None,
        ge=1,
    )

    section_title: str | None = Field(
        default=None,
        max_length=300,
    )

    # Позиции фрагмента в полном извлечённом тексте документа.
    # Диапазон предполагается полуоткрытым: [char_start, char_end).
    char_start: int | None = Field(
        default=None,
        ge=0,
    )

    char_end: int | None = Field(
        default=None,
        ge=0,
    )

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_char_range(self) -> Chunk:
        """Проверяем корректность диапазона символов."""

        if (self.char_start is None) != (self.char_end is None):
            raise ValueError(
                "char_start и char_end должны быть указаны вместе"
            )

        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end <= self.char_start
        ):
            raise ValueError(
                "char_end должен быть больше char_start"
            )

        return self


class SearchFilters(APIModel):
    """Фильтры для поиска фрагментов в Qdrant."""

    document_ids: list[UUID] | None = None

    specialty: str | None = Field(
        default=None,
        max_length=100,
    )

    source_types: list[SourceType] | None = None

    lecture_date_from: date | None = None
    lecture_date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> SearchFilters:
        """Проверяем корректность диапазона дат."""

        if (
            self.lecture_date_from is not None
            and self.lecture_date_to is not None
            and self.lecture_date_from > self.lecture_date_to
        ):
            raise ValueError(
                "lecture_date_from не может быть позже lecture_date_to"
            )

        return self


class QueryRequest(APIModel):
    """Запрос на поиск релевантных фрагментов."""

    query: str = Field(
        min_length=2,
        max_length=5_000,
        description="Текст поискового запроса",
    )

    # K — количество лучших результатов, которые нужно вернуть.
    top_k: int = Field(
        default=20,
        ge=1,
        le=100,
    )

    use_reranker: bool = True

    # Сколько результатов retriever передаст reranker-у.
    rerank_top_k: int = Field(
        default=10,
        ge=1,
        le=100,
    )

    # Для cosine similarity значение теоретически лежит от -1 до 1.
    min_retrieval_score: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )

    filters: SearchFilters = Field(
        default_factory=SearchFilters,
    )

    @model_validator(mode="after")
    def validate_search_limits(self) -> QueryRequest:
        """Reranker не может обработать больше результатов, чем найдено."""

        if self.rerank_top_k > self.top_k:
            raise ValueError(
                "rerank_top_k не может быть больше top_k"
            )

        return self


class SearchResult(APIModel):
    """Один найденный фрагмент."""

    rank: int = Field(
        ge=1,
        description="Позиция результата в итоговой выдаче",
    )

    chunk: Chunk

    # Оценка retriever-а, то есть векторного поиска.
    retrieval_score: float

    # Оценка cross-encoder reranker-а.
    # None, если reranker не использовался.
    rerank_score: float | None = None

    # Итоговая оценка, по которой отсортирована выдача.
    final_score: float


class SearchResponse(APIModel):
    """Ответ endpoint-а поиска."""

    query: str

    results: list[SearchResult] = Field(default_factory=list)

    total_candidates: int = Field(
        ge=0,
        description="Количество кандидатов до финального отбора",
    )

    # ms означает milliseconds — миллисекунды.
    took_ms: float = Field(
        ge=0,
        description="Время выполнения запроса в миллисекундах",
    )


class AnswerRequest(QueryRequest):
    """
    Запрос на генерацию ответа.

    Наследуется от QueryRequest, потому что генерация ответа
    сначала выполняет тот же поиск фрагментов.
    """

    max_context_chunks: int = Field(
        default=8,
        ge=1,
        le=30,
        description="Максимальное число фрагментов в контексте LLM",
    )

    include_citations: bool = True

    @model_validator(mode="after")
    def validate_answer_limits(self) -> AnswerRequest:
        """Проверяем, что контекст не требует несуществующих фрагментов."""

        available_chunks = (
            self.rerank_top_k
            if self.use_reranker
            else self.top_k
        )

        if self.max_context_chunks > available_chunks:
            raise ValueError(
                "max_context_chunks не может быть больше количества "
                "фрагментов после поиска"
            )

        return self


class Citation(APIModel):
    """
    Ссылка ответа на конкретный фрагмент документа.

    Citation означает цитирование или ссылку на источник.
    """

    document_id: UUID
    chunk_id: UUID
    document_title: str

    page_number: int | None = Field(
        default=None,
        ge=1,
    )

    section_title: str | None = None

    quote: str = Field(
        min_length=1,
        description="Текст, подтверждающий часть ответа",
    )

    char_start: int | None = Field(
        default=None,
        ge=0,
    )

    char_end: int | None = Field(
        default=None,
        ge=0,
    )

    retrieval_score: float | None = None
    rerank_score: float | None = None

    @model_validator(mode="after")
    def validate_char_range(self) -> Citation:
        """Проверяем диапазон символов цитаты."""

        if (self.char_start is None) != (self.char_end is None):
            raise ValueError(
                "char_start и char_end должны быть указаны вместе"
            )

        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end <= self.char_start
        ):
            raise ValueError(
                "char_end должен быть больше char_start"
            )

        return self


class AnswerOut(APIModel):
    """Ответ RAG-системы."""

    answer: str = Field(min_length=1)

    citations: list[Citation] = Field(default_factory=list)

    # Это наша прикладная оценка уверенности,
    # а не математически гарантированная вероятность.
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    limitations: list[str] = Field(default_factory=list)

    safety_notes: list[str] = Field(default_factory=list)

    used_chunks: int = Field(ge=0)

    took_ms: float = Field(ge=0)


class ErrorOut(APIModel):
    """Единый формат ошибок API."""

    # Машиночитаемый код, например document_not_found.
    code: str = Field(
        min_length=1,
        max_length=100,
    )

    # Человекочитаемое описание ошибки.
    detail: str = Field(min_length=1)

    context: dict[str, Any] = Field(default_factory=dict)


class HealthOut(APIModel):
    """Состояние приложения и его зависимостей."""

    status: str
    postgres: str
    qdrant: str
    embedding_model: str