from __future__ import annotations

import asyncio
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.config import Settings

_WORD_PATTERN = re.compile(r"[\wёЁ]+", re.UNICODE)


class RerankService(ABC):
    backend_name: str

    @abstractmethod
    async def score(self, query: str, documents: Sequence[str]) -> list[float]:
        raise NotImplementedError


class LexicalRerankService(RerankService):
    backend_name = "lexical"

    async def score(self, query: str, documents: Sequence[str]) -> list[float]:
        query_words = [word.lower() for word in _WORD_PATTERN.findall(query)]
        query_set = set(query_words)
        if not query_set:
            return [0.0] * len(documents)
        scores: list[float] = []
        normalized_query = " ".join(query_words)
        for document in documents:
            words = [word.lower() for word in _WORD_PATTERN.findall(document)]
            document_set = set(words)
            overlap = len(query_set & document_set) / len(query_set)
            density = len(query_set & document_set) / max(1, len(document_set))
            phrase_bonus = 0.15 if normalized_query in " ".join(words) else 0.0
            scores.append(min(1.0, 0.8 * overlap + 0.2 * density + phrase_bonus))
        return scores


class CrossEncoderRerankService(RerankService):
    backend_name = "cross-encoder"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._lock = asyncio.Lock()

    async def _get_model(self):
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import CrossEncoder
                except ImportError as exc:
                    raise RuntimeError(
                        "sentence-transformers is not installed; install requirements-ml.txt"
                    ) from exc
                kwargs = {}
                if self._settings.reranker_device != "auto":
                    kwargs["device"] = self._settings.reranker_device
                self._model = await asyncio.to_thread(
                    CrossEncoder,
                    self._settings.reranker_model_name,
                    **kwargs,
                )
        return self._model

    async def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        model = await self._get_model()
        raw_scores = await asyncio.to_thread(
            model.predict,
            [(query, document) for document in documents],
            batch_size=self._settings.reranker_batch_size,
            show_progress_bar=False,
        )
        return [1.0 / (1.0 + math.exp(-float(score))) for score in raw_scores]


def create_rerank_service(settings: Settings) -> RerankService:
    if settings.reranker_backend == "cross-encoder":
        return CrossEncoderRerankService(settings)
    return LexicalRerankService()
