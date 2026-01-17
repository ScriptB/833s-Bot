from __future__ import annotations

import aiosqlite
import json

from .base import BaseService


class GiveawaysStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS giveaways (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                ends_ts INTEGER NOT NULL,
                winners INTEGER NOT NULL,
                prize TEXT NOT NULL,
                entries_json TEXT NOT NULL DEFAULT '[]',
                ended INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, message_id)
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_giveaways_ends ON giveaways(ends_ts)")
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Giveaways don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM giveaways WHERE guild_id = ? AND message_id = ?"

    async def create(self, guild_id: int, channel_id: int, message_id: int, ends_ts: int, winners: int, prize: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO giveaways (guild_id, channel_id, message_id, ends_ts, winners, prize, entries_json, ended) "
                "VALUES (?, ?, ?, ?, ?, ?, '[]', 0)",
                (int(guild_id), int(channel_id), int(message_id), int(ends_ts), int(winners), prize),
            )
            await db.commit()

    async def add_entry(self, guild_id: int, message_id: int, user_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT entries_json FROM giveaways WHERE guild_id=? AND message_id=?",
                (int(guild_id), int(message_id)),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return 0
            entries = json.loads(row[0] or "[]")
            uid = int(user_id)
            if uid not in entries:
                entries.append(uid)
            await db.execute(
                "UPDATE giveaways SET entries_json=? WHERE guild_id=? AND message_id=?",
                (json.dumps(entries), int(guild_id), int(message_id)),
            )
            await db.commit()
        return len(entries)

    async def remove_entry(self, guild_id: int, message_id: int, user_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT entries_json FROM giveaways WHERE guild_id=? AND message_id=?",
                (int(guild_id), int(message_id)),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return 0
            entries = json.loads(row[0] or "[]")
            uid = int(user_id)
            if uid in entries:
                entries.remove(uid)
            await db.execute(
                "UPDATE giveaways SET entries_json=? WHERE guild_id=? AND message_id=?",
                (json.dumps(entries), int(guild_id), int(message_id)),
            )
            await db.commit()
        return len(entries)

    async def due(self, now_ts: int, limit: int = 20):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT guild_id, channel_id, message_id, ends_ts, winners, prize, entries_json FROM giveaways "
                "WHERE ended=0 AND ends_ts <= ? ORDER BY ends_ts ASC LIMIT ?",
                (int(now_ts), int(limit)),
            ) as cur:
                return await cur.fetchall()

    async def list_open(self, limit: int = 200):
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT guild_id, message_id FROM giveaways WHERE ended=0 ORDER BY ends_ts ASC LIMIT ?",
                (int(limit),),
            ) as cur:
                return await cur.fetchall()

    async def mark_ended(self, guild_id: int, message_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE giveaways SET ended=1 WHERE guild_id=? AND message_id=?",
                (int(guild_id), int(message_id)),
            )
            await db.commit()
