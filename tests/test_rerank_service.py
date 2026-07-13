import pytest

from app.services.rerank_service import LexicalRerankService


@pytest.mark.asyncio
async def test_lexical_reranker_prefers_matching_document() -> None:
    scores = await LexicalRerankService().score(
        "препараты при гипертензии",
        ["Препараты при гипертензии включают ингибиторы АПФ", "Переломы костей"],
    )
    assert scores[0] > scores[1]
    assert all(0 <= score <= 1 for score in scores)
