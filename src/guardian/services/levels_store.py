from __future__ import annotations

import aiosqlite

from .base import BaseService


class LevelsStore(BaseService):
    def __init__(self, sqlite_path: str, cache_ttl: int = 300) -> None:
        super().__init__(sqlite_path, cache_ttl)

    async def _create_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS levels (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                total_xp INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        # best-effort migration from older schema without total_xp
        async with db.execute("PRAGMA table_info(levels)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        if "total_xp" not in cols:
            await db.execute("ALTER TABLE levels ADD COLUMN total_xp INTEGER NOT NULL DEFAULT 0")
    
    def _from_row(self, row: aiosqlite.Row) -> None:
        # Levels don't need a specific data class for now
        return None
    
    @property
    def _get_query(self) -> str:
        return "SELECT * FROM levels WHERE guild_id = ? AND user_id = ?"

    @staticmethod
    def xp_for_next(level: int) -> int:
        return int(100 + 5 * (level ** 2) + 50 * level)

    async def add_xp(self, guild_id: int, user_id: int, amount: int) -> tuple[int, int, bool]:
        amount = max(0, int(amount))
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT total_xp, xp, level FROM levels WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            ) as cur:
                row = await cur.fetchone()
            total_xp, xp, level = row if row else (0, 0, 0)

            total_xp += amount
            xp += amount

            leveled = False
            while xp >= self.xp_for_next(level):
                xp -= self.xp_for_next(level)
                level += 1
                leveled = True

            await db.execute(
                """
                INSERT INTO levels (guild_id, user_id, total_xp, xp, level)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_xp=excluded.total_xp,
                    xp=excluded.xp,
                    level=excluded.level
                """,
                (int(guild_id), int(user_id), int(total_xp), int(xp), int(level)),
            )
            await db.commit()
        return int(xp), int(level), bool(leveled)

    async def get(self, guild_id: int, user_id: int) -> tuple[int, int, int]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT total_xp, xp, level FROM levels WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            ) as cur:
                row = await cur.fetchone()
        return (int(row[0]), int(row[1]), int(row[2])) if row else (0, 0, 0)

    async def reset_user(self, guild_id: int, user_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "DELETE FROM levels WHERE guild_id=? AND user_id=?",
                (int(guild_id), int(user_id)),
            )
            await db.commit()

    async def reset_guild(self, guild_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM levels WHERE guild_id=?", (int(guild_id),))
            await db.commit()

    async def leaderboard(self, guild_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT user_id, level, total_xp
                FROM levels
                WHERE guild_id=?
                ORDER BY level DESC, total_xp DESC
                LIMIT ?
                """,
                (int(guild_id), int(limit)),
            ) as cur:
                rows = await cur.fetchall()
        return [(int(uid), int(lvl), int(txp)) for (uid, lvl, txp) in rows]
