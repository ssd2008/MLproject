from __future__ import annotations

import gc

from app.config import settings


def main() -> None:
    try:
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed; build the image with requirements-ml.txt"
        ) from exc

    embedding_device = "cpu" if settings.embedding_device == "auto" else settings.embedding_device
    reranker_device = "cpu" if settings.reranker_device == "auto" else settings.reranker_device

    print(f"Downloading embedding model: {settings.embedding_model_name}", flush=True)
    embedding_model = SentenceTransformer(
        settings.embedding_model_name,
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

    print(f"Downloading reranker model: {settings.reranker_model_name}", flush=True)
    reranker_model = CrossEncoder(
        settings.reranker_model_name,
        device=reranker_device,
    )
    del reranker_model
    gc.collect()

    print("ML models are available in the Hugging Face cache", flush=True)


if __name__ == "__main__":
    main()
