from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from evaluation.benchmark_lib import (
    BM25Retriever,
    Chunk,
    Question,
    SearchHit,
    aggregate,
    evaluate_query,
)
from evaluation.prepare_dataset import (
    SOURCE_SPECS,
    SourceSpec,
    _deduplicate,
    _download,
    _parse_document,
    prepare_dataset,
)


class _DummyResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _DummyResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class BM25Tests(unittest.TestCase):
    def test_relevant_document_is_ranked_first(self) -> None:
        chunks = [
            Chunk("a", "d1", "A", "u", "growth hormone pituitary adenoma", "CC", "q1", "causes"),
            Chunk("b", "d2", "B", "u", "gluten damages intestinal villi", "CC", "q2", "information"),
        ]
        retriever = BM25Retriever(chunks)
        hits = retriever.search("Which disorder involves gluten and villi?", top_k=2)
        self.assertEqual(hits[0].chunk_id, "b")


class MetricTests(unittest.TestCase):
    def test_metrics_use_first_gold_rank_and_top1_citation(self) -> None:
        question = Question("q", "question", "d", ("gold",), "type", "original", ("source",))
        row = evaluate_query(
            configuration="test",
            question=question,
            hits=[SearchHit("wrong", 1.0), SearchHit("gold", 0.5)],
            latency_seconds=0.2,
        )
        self.assertEqual(row.rank, 2)
        self.assertEqual(row.recall_at_5, 1.0)
        self.assertEqual(row.reciprocal_rank, 0.5)
        self.assertEqual(row.citation_supported, 0.0)

    def test_aggregate(self) -> None:
        question = Question("q", "question", "d", ("gold",), "type", "original", ("source",))
        rows = [
            evaluate_query(
                configuration="test",
                question=question,
                hits=[SearchHit("gold", 1.0)],
                latency_seconds=0.1,
            ),
            evaluate_query(
                configuration="test",
                question=question,
                hits=[SearchHit("wrong", 1.0)],
                latency_seconds=0.3,
            ),
        ]
        summary = aggregate(rows)
        self.assertAlmostEqual(summary["recall_at_5"], 0.5)
        self.assertAlmostEqual(summary["mrr"], 0.5)
        self.assertAlmostEqual(summary["citation_accuracy"], 0.5)
        self.assertAlmostEqual(summary["latency_p50_seconds"], 0.2)


class DatasetTests(unittest.TestCase):
    def test_xml_parsing_and_duplicate_gold_merge(self) -> None:
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<Document id='1' source='NIDDK' url='https://example.test/source'>
<Focus>Example Disease</Focus><QAPairs>
<QAPair pid='1'><Question qid='1-1' qtype='symptoms'>What are the symptoms?</Question><Answer>Fever and fatigue.</Answer></QAPair>
<QAPair pid='2'><Question qid='1-2' qtype='symptoms'>What are the symptoms?</Question><Answer>Headache.</Answer></QAPair>
</QAPairs></Document>"""
        spec = SourceSpec("example", "Example Disease", "example.xml")
        chunks, candidates = _parse_document(spec, xml)
        self.assertEqual(len(chunks), 2)
        deduplicated = _deduplicate(candidates)
        originals = [item for item in deduplicated if item["question"] == "What are the symptoms?"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(len(originals[0]["gold_chunk_ids"]), 2)

    def test_download_uses_github_api_fallback_after_tls_failure(self) -> None:
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<Document id='1'><Focus>Example</Focus><QAPairs /></Document>"""
        with patch(
            "evaluation.prepare_dataset.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("unexpected TLS EOF"), _DummyResponse(xml)],
        ) as urlopen:
            payload = _download(SOURCE_SPECS[0], attempts=1, base_delay_seconds=0)
        self.assertEqual(payload, xml)
        self.assertEqual(urlopen.call_count, 2)

    def test_bundled_dataset_builds_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "evaluation.prepare_dataset._download",
                side_effect=AssertionError("network access was not expected"),
            ):
                summary = prepare_dataset(
                    Path(temporary_directory),
                    target_questions=60,
                    refresh=False,
                )
        self.assertEqual(summary["documents"], 3)
        self.assertEqual(summary["chunks"], 18)
        self.assertEqual(summary["questions"], 60)
        self.assertEqual(summary["original_questions"], 15)
        self.assertEqual(summary["paraphrased_questions"], 45)


if __name__ == "__main__":
    unittest.main()
