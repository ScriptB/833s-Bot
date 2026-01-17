from __future__ import annotations

import time
from collections import deque


class JoinVelocity:
    def __init__(self, window_seconds: int = 60, threshold: int = 8) -> None:
        self.window_seconds = window_seconds
        self.threshold = threshold
        self._joins = deque()

    def record(self) -> bool:
        now = time.time()
        self._joins.append(now)
        while self._joins and (now - self._joins[0]) > self.window_seconds:
            self._joins.popleft()
        return len(self._joins) >= self.threshold
