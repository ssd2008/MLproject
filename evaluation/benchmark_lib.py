from __future__ import annotations

import csv
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Sequence

_WORD_PATTERN = re.compile(r"[\wёЁ]+", re.UNICODE)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    source_url: str
    text: str
    license: str
    source_question_id: str
    question_type: str


@dataclass(frozen=True)
class Question:
    question_id: str
    question: str
    document_id: str
    gold_chunk_ids: tuple[str, ...]
    question_type: str
    provenance: str
    source_question_ids: tuple[str, ...]


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    score: float


@dataclass(frozen=True)
class QueryEvaluation:
    configuration: str
    question_id: str
    rank: int | None
    recall_at_5: float
    reciprocal_rank: float
    citation_supported: float
    latency_seconds: float
    top_chunk_id: str | None
    returned_chunk_ids: tuple[str, ...]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _WORD_PATTERN.findall(text)]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return records


def load_chunks(path: Path) -> list[Chunk]:
    return [Chunk(**record) for record in read_jsonl(path)]


def load_questions(path: Path) -> list[Question]:
    questions: list[Question] = []
    for record in read_jsonl(path):
        questions.append(
            Question(
                question_id=record["question_id"],
                question=record["question"],
                document_id=record["document_id"],
                gold_chunk_ids=tuple(record["gold_chunk_ids"]),
                question_type=record["question_type"],
                provenance=record["provenance"],
                source_question_ids=tuple(record["source_question_ids"]),
            )
        )
    return questions


class BM25Retriever:
    """Okapi BM25 (Best Matching 25) lexical retriever."""

    def __init__(self, chunks: Sequence[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        if not chunks:
            raise ValueError("BM25 requires at least one corpus chunk")
        self._chunks = list(chunks)
        self._k1 = k1
        self._b = b
        self._documents = [tokenize(chunk.text) for chunk in chunks]
        self._document_lengths = [len(document) for document in self._documents]
        self._average_document_length = statistics.fmean(self._document_lengths)
        self._term_frequencies = [Counter(document) for document in self._documents]
        self._document_frequencies: Counter[str] = Counter()
        for document in self._documents:
            self._document_frequencies.update(set(document))
        self._document_count = len(self._documents)

    def _inverse_document_frequency(self, term: str) -> float:
        document_frequency = self._document_frequencies.get(term, 0)
        return math.log(1.0 + (self._document_count - document_frequency + 0.5) / (document_frequency + 0.5))

    def search(self, query: str, *, top_k: int) -> list[SearchHit]:
        query_terms = tokenize(query)
        scored: list[SearchHit] = []
        for index, chunk in enumerate(self._chunks):
            score = 0.0
            document_length = self._document_lengths[index]
            length_normalization = 1.0 - self._b + self._b * document_length / self._average_document_length
            frequencies = self._term_frequencies[index]
            for term in query_terms:
                term_frequency = frequencies.get(term, 0)
                if term_frequency == 0:
                    continue
                numerator = term_frequency * (self._k1 + 1.0)
                denominator = term_frequency + self._k1 * length_normalization
                score += self._inverse_document_frequency(term) * numerator / denominator
            scored.append(SearchHit(chunk_id=chunk.chunk_id, score=score))
        scored.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return scored[:top_k]


class DenseRetriever:
    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        model_name: str,
        batch_size: int,
        device: str,
    ) -> None:
        self._chunks = list(chunks)
        self._model_name = model_name
        self._batch_size = batch_size
        self._device = device
        self._model = None
        self._matrix = None

    def build(self) -> None:
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Install evaluation/requirements.txt before running dense retrieval") from exc

        self._model = SentenceTransformer(self._model_name, device=self._device)
        passages = [f"passage: {chunk.text}" for chunk in self._chunks]
        self._matrix = self._model.encode(
            passages,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        ).astype(np.float32)

    def search(self, query: str, *, top_k: int) -> list[SearchHit]:
        if self._model is None or self._matrix is None:
            raise RuntimeError("DenseRetriever.build() must be called before search()")
        query_vector = self._model.encode(
            [f"query: {query}"],
            batch_size=1,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )[0]
        scores = self._matrix @ query_vector
        order = scores.argsort()[::-1][:top_k]
        return [SearchHit(chunk_id=self._chunks[int(index)].chunk_id, score=float(scores[index])) for index in order]


class CrossEncoderReranker:
    def __init__(
        self,
        chunks: Sequence[Chunk],
        dense_retriever: DenseRetriever,
        *,
        model_name: str,
        batch_size: int,
        device: str,
        candidate_k: int,
    ) -> None:
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self._dense_retriever = dense_retriever
        self._model_name = model_name
        self._batch_size = batch_size
        self._device = device
        self._candidate_k = candidate_k
        self._model = None

    def build(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Install evaluation/requirements.txt before running the reranker") from exc
        self._model = CrossEncoder(self._model_name, device=self._device)

    def search(self, query: str, *, top_k: int) -> list[SearchHit]:
        if self._model is None:
            raise RuntimeError("CrossEncoderReranker.build() must be called before search()")
        candidates = self._dense_retriever.search(query, top_k=self._candidate_k)
        pairs = [(query, self._chunks_by_id[hit.chunk_id].text) for hit in candidates]
        raw_scores = self._model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        reranked = [
            SearchHit(chunk_id=candidate.chunk_id, score=float(score))
            for candidate, score in zip(candidates, raw_scores, strict=True)
        ]
        reranked.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return reranked[:top_k]


def evaluate_query(
    *,
    configuration: str,
    question: Question,
    hits: Sequence[SearchHit],
    latency_seconds: float,
) -> QueryEvaluation:
    gold = set(question.gold_chunk_ids)
    rank: int | None = None
    for index, hit in enumerate(hits, start=1):
        if hit.chunk_id in gold:
            rank = index
            break
    top_chunk_id = hits[0].chunk_id if hits else None
    return QueryEvaluation(
        configuration=configuration,
        question_id=question.question_id,
        rank=rank,
        recall_at_5=float(rank is not None and rank <= 5),
        reciprocal_rank=0.0 if rank is None else 1.0 / rank,
        citation_supported=float(top_chunk_id in gold if top_chunk_id is not None else False),
        latency_seconds=latency_seconds,
        top_chunk_id=top_chunk_id,
        returned_chunk_ids=tuple(hit.chunk_id for hit in hits),
    )


def aggregate(rows: Sequence[QueryEvaluation]) -> dict[str, float]:
    if not rows:
        raise ValueError("Cannot aggregate an empty evaluation")
    latencies = [row.latency_seconds for row in rows]
    ordered = sorted(latencies)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "recall_at_5": statistics.fmean(row.recall_at_5 for row in rows),
        "mrr": statistics.fmean(row.reciprocal_rank for row in rows),
        "citation_accuracy": statistics.fmean(row.citation_supported for row in rows),
        "latency_p50_seconds": statistics.median(latencies),
        "latency_p95_seconds": ordered[p95_index],
        "latency_mean_seconds": statistics.fmean(latencies),
    }


def timed_search(search_function: Any, question: str, *, top_k: int) -> tuple[list[SearchHit], float]:
    started = perf_counter()
    hits = search_function(question, top_k=top_k)
    return hits, perf_counter() - started


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_summary_files(results_dir: Path, summaries: Sequence[dict[str, Any]]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "benchmark_results.csv"
    fieldnames = [
        "configuration",
        "recall_at_5",
        "mrr",
        "citation_accuracy",
        "latency_p50_seconds",
        "latency_p95_seconds",
        "latency_mean_seconds",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)

    markdown_lines = [
        "| Конфигурация | Recall@5 | MRR | Подтверждённые ответы | Задержка p50 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        markdown_lines.append(
            "| {configuration} | {recall_at_5:.3f} | {mrr:.3f} | {citation_accuracy:.1%} | {latency_p50_seconds:.3f} сек. |".format(
                **summary
            )
        )
    (results_dir / "benchmark_results.md").write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")


def evaluations_to_records(rows: Sequence[QueryEvaluation]) -> list[dict[str, Any]]:
    return [asdict(row) for row in rows]
