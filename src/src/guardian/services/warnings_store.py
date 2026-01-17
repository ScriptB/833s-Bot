from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from typing import Optional

from .base import BaseService


@dataclass(frozen=True)
class WarningRecord:
    id: int
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    created_at_iso: str


class WarningsStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              guild_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              moderator_id INTEGER NOT NULL,
              reason TEXT NOT NULL,
              created_at_iso TEXT NOT NULL
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id)")
    
    def _from_row(self, row: aiosqlite.Row) -> WarningRecord:
        return WarningRecord(
            id=row["id"],
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            moderator_id=row["moderator_id"],
            reason=row["reason"],
            created_at_iso=row["created_at_iso"]
        )
    
    @property
    def _get_query(self) -> str:
        return "SELECT id, guild_id, user_id, moderator_id, reason, created_at_iso FROM warnings WHERE id = ?"

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str, created_at_iso: str) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at_iso) VALUES (?, ?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, reason, created_at_iso),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def list_warnings(self, guild_id: int, user_id: int, limit: int = 20) -> list[WarningRecord]:
        limit = max(1, min(100, int(limit)))
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, guild_id, user_id, moderator_id, reason, created_at_iso FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [self._from_row(row) for row in rows]

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            await db.commit()
            return int(cur.rowcount)
