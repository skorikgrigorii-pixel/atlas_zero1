from __future__ import annotations

from collections import deque
from typing import Any


class JobQueue:
    """Simple FIFO queue used by the media orchestrator."""

    def __init__(self, jobs: list[dict[str, Any]] | None = None):
        self._queue = deque(jobs or [])

    def enqueue(self, job: dict[str, Any]) -> dict[str, Any]:
        self._queue.append(job)
        return job

    def dequeue(self) -> dict[str, Any] | None:
        return self._queue.popleft() if self._queue else None

    def retry(self, job: dict[str, Any]) -> dict[str, Any]:
        self._queue.appendleft(job)
        return job

    def size(self) -> int:
        return len(self._queue)
