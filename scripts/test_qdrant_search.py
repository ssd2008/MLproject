import os

import torch.nn as nn
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer


load_dotenv()

host = os.getenv("QDRANT_HOST", "localhost")
port = os.getenv("QDRANT_PORT", "6333")
collection_name = os.getenv("QDRANT_COLLECTION", "medical_chunks")
model_name = os.getenv("EMBEDDING_MODEL_NAME")

client = QdrantClient(url=f"http://{host}:{port}")
model = SentenceTransformer(model_name)

text = (
    "Основные группы препаратов для лечения артериальной гипертензии: "
    "ингибиторы АПФ, блокаторы рецепторов ангиотензина II, диуретики, "
    "блокаторы кальциевых каналов и бета-блокаторы."
)

vector = model.encode(text, normalize_embeddings=True).tolist()

client.upsert(
    collection_name=collection_name,
    points=[
        PointStruct(
            id=1,
            vector=vector,
            payload={
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "document_title": "Тестовая лекция по гипертензии",
                "text": text,
                "source_type": "lecture",
                "specialty": "cardiology",
                "language": "ru",
                "page": 1,
                "section": "Лечение",
            },
        )
    ],
)

query = "Какие препараты применяются при гипертензии?"
query_vector = model.encode(query, normalize_embeddings=True).tolist()

result = client.query_points(
    collection_name=collection_name,
    query=query_vector,
    limit=3,
)

for point in result.points:
    print("score:", point.score)
    print("payload:", point.payload)
    print()