from __future__ import annotations

import aiosqlite
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, Any

from .cache import TTLCache

T = TypeVar("T")
log = logging.getLogger("guardian.base_service")


class BaseService(ABC, Generic[T]):
    """Base class for all SQLite-backed services with caching."""
    
    def __init__(self, sqlite_path: str, cache_ttl_seconds: int = 120) -> None:
        self._path = sqlite_path
        self._cache: TTLCache[int, T] = TTLCache(default_ttl_seconds=cache_ttl_seconds)
        self._logger = logging.getLogger(f"guardian.{self.__class__.__name__.lower()}")
    
    async def init(self) -> None:
        """Initialize the database schema."""
        async with aiosqlite.connect(self._path) as db:
            await self._create_tables(db)
            await db.commit()
    
    @abstractmethod
    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        """Create the necessary database tables."""
        pass
    
    @abstractmethod
    def _from_row(self, row: aiosqlite.Row) -> T:
        """Convert a database row to the service's data type."""
        pass
    
    async def get(self, key: int) -> Optional[T]:
        """Get cached data or fetch from database."""
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(self._get_query, (key,)) as cur:
                row = await cur.fetchone()
                if row is None:
                    return None
                
                data = self._from_row(row)
                self._cache.set(key, data)
                return data
    
    @property
    @abstractmethod
    def _get_query(self) -> str:
        """SQL query for getting data by key."""
        pass
