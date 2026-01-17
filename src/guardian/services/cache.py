from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _Entry(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    """In-memory TTL cache."""

    def __init__(self, default_ttl_seconds: int = 120) -> None:
        self._default_ttl = max(1, int(default_ttl_seconds))
        self._store: dict[K, _Entry[V]] = {}

    def get(self, key: K) -> Optional[V]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: K, value: V, ttl_seconds: Optional[int] = None) -> None:
        ttl = self._default_ttl if ttl_seconds is None else max(1, int(ttl_seconds))
        self._store[key] = _Entry(value=value, expires_at=time.time() + ttl)

    def delete(self, key: K) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def prune(self) -> int:
        now = time.time()
        stale = [k for k, v in self._store.items() if v.expires_at < now]
        for k in stale:
            self._store.pop(k, None)
        return len(stale)
