from __future__ import annotations

import asyncio
import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.config import Settings

_WORD_PATTERN = re.compile(r"[\wёЁ]+", re.UNICODE)


class EmbeddingService(ABC):
    dimension: int
    backend_name: str

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class HashEmbeddingService(EmbeddingService):
    """Dependency-free feature hashing backend for development and tests."""

    backend_name = "hash"

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        words = [word.lower() for word in _WORD_PATTERN.findall(text)]
        features = words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class SentenceTransformerEmbeddingService(EmbeddingService):
    backend_name = "sentence-transformers"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.dimension = settings.embedding_dimension
        self._model = None
        self._lock = asyncio.Lock()

    async def _get_model(self):
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise RuntimeError(
                        "sentence-transformers is not installed; install requirements-ml.txt"
                    ) from exc
                kwargs = {}
                if self._settings.embedding_device != "auto":
                    kwargs["device"] = self._settings.embedding_device
                self._model = await asyncio.to_thread(
                    SentenceTransformer,
                    self._settings.embedding_model_name,
                    **kwargs,
                )
                actual_dimension = self._model.get_sentence_embedding_dimension()
                if actual_dimension != self.dimension:
                    raise RuntimeError(
                        f"Embedding dimension mismatch: model={actual_dimension}, settings={self.dimension}"
                    )
        return self._model

    async def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        model = await self._get_model()
        embeddings = await asyncio.to_thread(
            model.encode,
            list(texts),
            batch_size=self._settings.embedding_batch_size,
            normalize_embeddings=self._settings.normalize_embeddings,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.astype("float32").tolist()

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._encode([f"passage: {text}" for text in texts])

    async def embed_query(self, text: str) -> list[float]:
        return (await self._encode([f"query: {text}"]))[0]


def create_embedding_service(settings: Settings) -> EmbeddingService:
    if settings.embedding_backend == "sentence-transformers":
        return SentenceTransformerEmbeddingService(settings)
    return HashEmbeddingService(settings.embedding_dimension)
