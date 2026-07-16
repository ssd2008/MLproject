from __future__ import annotations

import time

from app.repositories.vector_repository import VectorRepository, VectorSearchResult
from app.schemas import QueryRequest, SearchResponse, SearchResult
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService


class SearchService:
    def __init__(
        self,
        *,
        vectors: VectorRepository,
        embeddings: EmbeddingService,
        reranker: RerankService,
    ) -> None:
        self._vectors = vectors
        self._embeddings = embeddings
        self._reranker = reranker

    async def search(self, request: QueryRequest) -> SearchResponse:
        started = time.perf_counter()
        query_vector = await self._embeddings.embed_query(request.query)
        candidates = await self._vectors.search(
            query_vector,
            limit=request.candidate_k,
            score_threshold=request.min_retrieval_score,
            filters=request.filters,
        )
        rerank_scores: list[float | None]
        if request.use_reranker and candidates:
            rerank_scores = list(
                await self._reranker.score(
                    request.query,
                    [candidate.payload.text for candidate in candidates],
                )
            )
        else:
            rerank_scores = [None] * len(candidates)

        ranked = [
            (candidate, rerank_score, self._final_score(candidate, rerank_score))
            for candidate, rerank_score in zip(candidates, rerank_scores, strict=True)
        ]
        ranked.sort(key=lambda item: item[2], reverse=True)
        results = [
            self._to_result(rank, candidate, rerank_score, final_score)
            for rank, (candidate, rerank_score, final_score) in enumerate(
                ranked[: request.top_k],
                start=1,
            )
        ]
        return SearchResponse(
            query=request.query,
            results=results,
            total_candidates=len(candidates),
            took_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _final_score(candidate: VectorSearchResult, rerank_score: float | None) -> float:
        retrieval_normalized = max(0.0, min(1.0, (candidate.score + 1.0) / 2.0))
        return (
            retrieval_normalized
            if rerank_score is None
            else 0.25 * retrieval_normalized + 0.75 * rerank_score
        )

    @staticmethod
    def _to_result(
        rank: int,
        candidate: VectorSearchResult,
        rerank_score: float | None,
        final_score: float,
    ) -> SearchResult:
        payload = candidate.payload
        return SearchResult(
            rank=rank,
            chunk_id=candidate.point_id,
            document_id=payload.document_id,
            document_title=payload.document_title,
            chunk_index=payload.chunk_index,
            text=payload.text,
            source_type=payload.source_type,
            source_url=payload.source_url,
            specialty=payload.specialty,
            lecture_date=payload.lecture_date,
            language=payload.language,
            page_start=payload.page_start,
            page_end=payload.page_end,
            time_start_seconds=payload.time_start_seconds,
            time_end_seconds=payload.time_end_seconds,
            section_title=payload.section_title,
            char_start=payload.char_start,
            char_end=payload.char_end,
            retrieval_score=candidate.score,
            rerank_score=rerank_score,
            final_score=final_score,
        )
