from __future__ import annotations

import time
import aiosqlite

from .base import BaseService


class SuggestionsStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestions (
                guild_id INTEGER NOT NULL,
                suggestion_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                message_id INTEGER NULL,
                status TEXT NOT NULL DEFAULT 'open',
                PRIMARY KEY (guild_id, suggestion_id)
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Suggestions don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM suggestions WHERE guild_id = ? AND suggestion_id = ?"

    async def next_id(self, guild_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT COALESCE(MAX(suggestion_id),0)+1 FROM suggestions WHERE guild_id=?", (int(guild_id),)) as cur:
                row = await cur.fetchone()
        return int(row[0]) if row else 1

    async def add(self, guild_id: int, author_id: int, content: str) -> int:
        sid = await self.next_id(guild_id)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO suggestions (guild_id, suggestion_id, author_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (int(guild_id), int(sid), int(author_id), str(content), int(time.time())),
            )
            await db.commit()
        return sid

    async def set_message(self, guild_id: int, suggestion_id: int, message_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE suggestions SET message_id=? WHERE guild_id=? AND suggestion_id=?",
                (int(message_id), int(guild_id), int(suggestion_id)),
            )
            await db.commit()
