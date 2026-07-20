from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from evaluation.benchmark_lib import (
    BM25Retriever,
    CrossEncoderReranker,
    DenseRetriever,
    aggregate,
    evaluate_query,
    evaluations_to_records,
    load_chunks,
    load_questions,
    timed_search,
    write_jsonl,
    write_summary_files,
)


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _hardware_metadata(device: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "device": device,
    }
    try:
        import torch

        metadata.update(
            {
                "torch": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "mps_available": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
            }
        )
    except ImportError:
        metadata["torch"] = None
    return metadata


def _run_configuration(
    *,
    name: str,
    search_function: Any,
    questions: list,
    top_k: int,
) -> list:
    if questions:
        search_function(questions[0].question, top_k=top_k)
    rows = []
    for index, question in enumerate(questions, start=1):
        hits, latency = timed_search(search_function, question.question, top_k=top_k)
        rows.append(
            evaluate_query(
                configuration=name,
                question=question,
                hits=hits,
                latency_seconds=latency,
            )
        )
        if index % 10 == 0 or index == len(questions):
            print(f"[{name}] {index}/{len(questions)}")
    return rows


def run_benchmark(
    *,
    data_dir: Path,
    results_dir: Path,
    config_path: Path,
    device_override: str | None,
    include_bm25: bool,
    with_reranker: bool,
) -> list[dict[str, Any]]:
    config = _load_config(config_path)
    device = device_override or config["device"]
    chunks = load_chunks(data_dir / "corpus.jsonl")
    questions = load_questions(data_dir / "questions.jsonl")
    if not chunks or not questions:
        raise ValueError("Dataset is empty. Run python -m evaluation.prepare_dataset first.")

    top_k = int(config["top_k"])
    configurations: list[tuple[str, Any]] = []

    if include_bm25:
        bm25 = BM25Retriever(chunks, k1=float(config["bm25_k1"]), b=float(config["bm25_b"]))
        configurations.append(("BM25", bm25.search))

    dense = DenseRetriever(
        chunks,
        model_name=config["embedding_model"],
        batch_size=int(config["dense_batch_size"]),
        device=device,
    )
    print(f"Building dense index with {config['embedding_model']}...")
    dense.build()
    configurations.append(("Dense", dense.search))

    if with_reranker:
        candidate_k = max(int(config["candidate_k"]), top_k)
        reranker = CrossEncoderReranker(
            chunks,
            dense,
            model_name=config["reranker_model"],
            batch_size=int(config["reranker_batch_size"]),
            device=device,
            candidate_k=candidate_k,
        )
        print(f"Loading optional reranker {config['reranker_model']}...")
        reranker.build()
        configurations.append(("Dense + reranker", reranker.search))

    all_rows = []
    summaries: list[dict[str, Any]] = []
    for name, search_function in configurations:
        rows = _run_configuration(name=name, search_function=search_function, questions=questions, top_k=top_k)
        all_rows.extend(rows)
        summaries.append({"configuration": name, **aggregate(rows)})

    results_dir.mkdir(parents=True, exist_ok=True)
    write_summary_files(results_dir, summaries)
    write_jsonl(results_dir / "per_question.jsonl", evaluations_to_records(all_rows))
    metadata = {
        "dataset": {
            "documents": len({chunk.document_id for chunk in chunks}),
            "chunks": len(chunks),
            "questions": len(questions),
        },
        "config": config,
        "configurations": [name for name, _ in configurations],
        "effective_device": device,
        "hardware": _hardware_metadata(device),
        "latency_definition": "warm model; per-query retrieval; excludes model loading and corpus indexing",
        "citation_accuracy_definition": "top-1 cited chunk belongs to the annotated gold chunk set",
    }
    (results_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate dense retrieval; optionally include BM25 and the experimental reranker"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("evaluation/data"))
    parser.add_argument("--results-dir", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--config", type=Path, default=Path("evaluation/config.json"))
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), default=None)
    parser.add_argument(
        "--include-bm25",
        action="store_true",
        help="Include the lexical BM25 baseline in the report",
    )
    parser.add_argument(
        "--with-reranker",
        action="store_true",
        help="Include the optional cross-encoder reranker in the report",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summaries = run_benchmark(
        data_dir=args.data_dir,
        results_dir=args.results_dir,
        config_path=args.config,
        device_override=args.device,
        include_bm25=args.include_bm25,
        with_reranker=args.with_reranker,
    )
    print(json.dumps(summaries, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
