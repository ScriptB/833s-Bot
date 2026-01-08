from __future__ import annotations

import time
import aiosqlite


class AchievementsStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS achievements_unlocked (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    unlocked_at INTEGER NOT NULL,
                    meta TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (guild_id, user_id, code)
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_ach_g_u ON achievements_unlocked (guild_id, user_id, unlocked_at)")
            await db.commit()

    async def unlock(self, guild_id: int, user_id: int, code: str, *, meta: str = "") -> bool:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                INSERT OR IGNORE INTO achievements_unlocked (guild_id, user_id, code, unlocked_at, meta)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, code, now, meta),
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_user(self, guild_id: int, user_id: int) -> list[tuple[str, int, str]]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                SELECT code, unlocked_at, meta
                FROM achievements_unlocked
                WHERE guild_id=? AND user_id=?
                ORDER BY unlocked_at ASC
                """,
                (guild_id, user_id),
            )
            rows = await cur.fetchall()
            await cur.close()
            return [(str(r[0]), int(r[1]), str(r[2] or "")) for r in rows]

    async def leaderboard(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                SELECT user_id, COUNT(*) AS cnt
                FROM achievements_unlocked
                WHERE guild_id=?
                GROUP BY user_id
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (guild_id, int(limit)),
            )
            rows = await cur.fetchall()
            await cur.close()
            return [(int(r[0]), int(r[1])) for r in rows]
