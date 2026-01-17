from __future__ import annotations

import aiosqlite

from .base import BaseService


class RemindersStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NULL,
                due_ts INTEGER NOT NULL,
                message TEXT NOT NULL
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_ts)")
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Reminders don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM reminders WHERE id = ?"

    async def add(self, user_id: int, channel_id: int, guild_id: int | None, due_ts: int, message: str) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO reminders (user_id, channel_id, guild_id, due_ts, message) VALUES (?, ?, ?, ?, ?)",
                (int(user_id), int(channel_id), int(guild_id) if guild_id else None, int(due_ts), message),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def due(self, now_ts: int, limit: int = 50):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT id, user_id, channel_id, guild_id, due_ts, message FROM reminders WHERE due_ts <= ? ORDER BY due_ts ASC LIMIT ?",
                (int(now_ts), int(limit)),
            ) as cur:
                return await cur.fetchall()

    async def delete(self, reminder_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM reminders WHERE id=?", (int(reminder_id),))
            await db.commit()
