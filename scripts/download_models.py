from __future__ import annotations

import gc
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from app.config import settings

T = TypeVar("T")


def _load_with_retries(
    label: str,
    factory: Callable[[], T],
    *,
    attempts: int = 3,
) -> T:
    """Load a model, retrying transient network and cache I/O failures."""
    for attempt in range(1, attempts + 1):
        try:
            return factory()
        except (OSError, RuntimeError) as exc:
            if attempt == attempts:
                raise
            delay_seconds = attempt * 10
            print(
                f"{label} download failed on attempt {attempt}/{attempts}: {exc}",
                flush=True,
            )
            print(
                f"Retrying in {delay_seconds} seconds; cached partial files will be reused.",
                flush=True,
            )
            gc.collect()
            time.sleep(delay_seconds)
    raise RuntimeError(f"Unable to load {label}")


def _resolve_huggingface_model(model_name_or_path: str, *, label: str) -> str:
    """Return a local model path, downloading Hub repositories serially when needed."""
    local_path = Path(model_name_or_path)
    if local_path.exists():
        print(f"Using local {label}: {local_path}", flush=True)
        return str(local_path)

    from huggingface_hub import snapshot_download

    print(
        f"Downloading {label} repository with one worker: {model_name_or_path}",
        flush=True,
    )
    return _load_with_retries(
        label,
        lambda: snapshot_download(
            repo_id=model_name_or_path,
            max_workers=1,
        ),
    )


def main() -> None:
    try:
        from faster_whisper import WhisperModel
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "ML dependencies are not installed; build the image with requirements-ml.txt"
        ) from exc

    embedding_device = "cpu" if settings.embedding_device == "auto" else settings.embedding_device
    reranker_device = "cpu" if settings.reranker_device == "auto" else settings.reranker_device
    asr_device = "cpu" if settings.asr_device == "auto" else settings.asr_device

    embedding_source = _resolve_huggingface_model(
        settings.embedding_model_name,
        label="embedding model",
    )
    embedding_model = SentenceTransformer(
        embedding_source,
        device=embedding_device,
    )
    actual_dimension = embedding_model.get_sentence_embedding_dimension()
    if actual_dimension != settings.embedding_dimension:
        raise RuntimeError(
            "Embedding dimension mismatch: "
            f"model={actual_dimension}, settings={settings.embedding_dimension}"
        )
    del embedding_model
    gc.collect()

    if settings.reranker_enabled:
        reranker_source = _resolve_huggingface_model(
            settings.reranker_model_name,
            label="reranker model",
        )
        reranker_model = CrossEncoder(
            reranker_source,
            device=reranker_device,
        )
        del reranker_model
        gc.collect()
    else:
        print("Skipping reranker model: RERANKER_ENABLED=false", flush=True)

    if settings.asr_backend != "disabled":
        print(f"Downloading ASR model: {settings.asr_model_name}", flush=True)
        asr_model = _load_with_retries(
            "ASR model",
            lambda: WhisperModel(
                settings.asr_model_name,
                device=asr_device,
                compute_type=settings.asr_compute_type,
            ),
        )
        del asr_model
        gc.collect()

    print("Enabled ML models are available locally", flush=True)


if __name__ == "__main__":
    main()
