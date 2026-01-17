from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from .stats import RuntimeStats

log = logging.getLogger("guardian.queue")

TaskFn = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class QueuePolicy:
    max_batch: int = 4
    every_ms: int = 100
    max_queue_size: int = 10_000
    micro_sleep_seconds: float = 0.01


class TaskQueue:
    """Paced async task queue to smooth bulk actions and reduce API bursts."""

    def __init__(self, policy: QueuePolicy, stats: RuntimeStats) -> None:
        self._policy = policy
        self._stats = stats
        self._q: asyncio.Queue[TaskFn] = asyncio.Queue(maxsize=policy.max_queue_size)
        self._stop = asyncio.Event()
        self._runner: Optional[asyncio.Task[None]] = None

    def start(self) -> None:
        if self._runner and not self._runner.done():
            return
        self._stop.clear()
        self._runner = asyncio.create_task(self._run(), name="guardian-task-queue")
        log.info(
            "TaskQueue started (max_batch=%s every_ms=%s max_size=%s)",
            self._policy.max_batch,
            self._policy.every_ms,
            self._policy.max_queue_size,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._runner:
            await self._runner
        log.info("TaskQueue stopped")

    def size(self) -> int:
        return self._q.qsize()

    async def enqueue(self, fn: TaskFn) -> None:
        try:
            self._q.put_nowait(fn)
            self._stats.tasks_enqueued += 1
        except asyncio.QueueFull as e:
            raise RuntimeError("TaskQueue is full; refusing to enqueue more tasks") from e

    async def _run(self) -> None:
        tick_sleep = max(1, self._policy.every_ms) / 1000.0
        max_batch = max(1, self._policy.max_batch)
        micro = max(0.0, float(self._policy.micro_sleep_seconds))

        while not self._stop.is_set():
            batch: list[TaskFn] = []
            for _ in range(max_batch):
                try:
                    batch.append(self._q.get_nowait())
                except asyncio.QueueEmpty:
                    break

            if not batch:
                await asyncio.sleep(tick_sleep)
                continue

            for fn in batch:
                try:
                    await fn()
                    self._stats.tasks_executed += 1
                except Exception:
                    self._stats.tasks_failed += 1
                    log.exception("Queued task failed")
                finally:
                    self._q.task_done()

                if micro:
                    await asyncio.sleep(micro)

            await asyncio.sleep(tick_sleep)
