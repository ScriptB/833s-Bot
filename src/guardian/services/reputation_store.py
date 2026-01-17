from __future__ import annotations

import aiosqlite
import time

from .base import BaseService


class ReputationStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reputation (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                last_given_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Reputation don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM reputation WHERE guild_id = ? AND user_id = ?"

    async def get(self, guild_id: int, user_id: int) -> tuple[int, int]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT score, last_given_at FROM reputation WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            await self.set(guild_id, user_id, 0, 0)
            return (0, 0)
        return (int(row[0]), int(row[1]))

    async def set(self, guild_id: int, user_id: int, score: int, last_given_at: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO reputation (guild_id, user_id, score, last_given_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    score=excluded.score,
                    last_given_at=excluded.last_given_at
                """,
                (int(guild_id), int(user_id), int(score), int(last_given_at)),
            )
            await db.commit()

    async def give(self, guild_id: int, giver_id: int, target_id: int, delta: int, cooldown_seconds: int = 43200) -> tuple[bool, int]:
        now = int(time.time())
        _, last = await self.get(guild_id, giver_id)
        if now - last < cooldown_seconds:
            return (False, cooldown_seconds - (now - last))
        score, _ = await self.get(guild_id, target_id)
        score += int(delta)
        await self.set(guild_id, target_id, score, 0)
        giver_score, _ = await self.get(guild_id, giver_id)
        await self.set(guild_id, giver_id, giver_score, now)
        return (True, score)
