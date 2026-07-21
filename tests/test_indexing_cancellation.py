from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.exceptions import IndexingCancellationTimeoutError
from app.services.indexing_cancellation import IndexingCancellationRegistry


def test_cancel_document_sets_flag_and_waits_for_job() -> None:
    async def scenario() -> None:
        registry = IndexingCancellationRegistry()
        document_id = uuid4()
        job_id = uuid4()
        cancel_event = registry.prepare(job_id, document_id)

        cancellation = asyncio.create_task(
            registry.cancel_document(document_id, timeout_seconds=1.0)
        )
        await asyncio.sleep(0)

        assert cancel_event.is_set()
        assert not cancellation.done()

        registry.finish(job_id)
        await cancellation

    asyncio.run(scenario())


def test_cancel_document_times_out_without_finished_signal() -> None:
    async def scenario() -> None:
        registry = IndexingCancellationRegistry()
        document_id = uuid4()
        job_id = uuid4()
        registry.prepare(job_id, document_id)

        with pytest.raises(IndexingCancellationTimeoutError):
            await registry.cancel_document(document_id, timeout_seconds=0.01)

        registry.finish(job_id)

    asyncio.run(scenario())
