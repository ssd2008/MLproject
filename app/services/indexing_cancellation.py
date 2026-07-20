from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Event, Lock
from uuid import UUID

from app.exceptions import IndexingCancellationTimeoutError


@dataclass(slots=True)
class _CancellationEntry:
    document_id: UUID
    cancel_event: Event
    finished_event: asyncio.Event


class IndexingCancellationRegistry:
    """Tracks active indexing jobs and coordinates cooperative cancellation."""

    def __init__(self) -> None:
        self._entries: dict[UUID, _CancellationEntry] = {}
        self._lock = Lock()

    def prepare(self, job_id: UUID, document_id: UUID) -> Event:
        entry = _CancellationEntry(
            document_id=document_id,
            cancel_event=Event(),
            finished_event=asyncio.Event(),
        )
        with self._lock:
            self._entries[job_id] = entry
        return entry.cancel_event

    def get_cancel_event(self, job_id: UUID, document_id: UUID) -> Event:
        with self._lock:
            entry = self._entries.get(job_id)
        if entry is not None:
            return entry.cancel_event
        return self.prepare(job_id, document_id)

    def finish(self, job_id: UUID) -> None:
        with self._lock:
            entry = self._entries.pop(job_id, None)
        if entry is not None:
            entry.finished_event.set()

    async def cancel_document(self, document_id: UUID, *, timeout_seconds: float = 30.0) -> None:
        with self._lock:
            entries = [
                entry for entry in self._entries.values() if entry.document_id == document_id
            ]
            for entry in entries:
                entry.cancel_event.set()

        if not entries:
            return

        try:
            await asyncio.wait_for(
                asyncio.gather(*(entry.finished_event.wait() for entry in entries)),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise IndexingCancellationTimeoutError(
                "Indexing cancellation is still in progress; retry deletion shortly",
                context={"document_id": str(document_id)},
            ) from exc
