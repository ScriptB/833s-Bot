from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RuntimeStats:
    started_at: float = field(default_factory=time.time)
    tasks_enqueued: int = 0
    tasks_executed: int = 0
    tasks_failed: int = 0
    welcomes_sent: int = 0
    roles_assigned: int = 0
    messages_deleted: int = 0
    timeouts_applied: int = 0

    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)
