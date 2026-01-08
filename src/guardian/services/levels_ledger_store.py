from __future__ import annotations

import aiosqlite
from datetime import date


class LevelsLedgerStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS xp_ledger (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, day)
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_xp_ledger_guild_day ON xp_ledger(guild_id, day)")
            await db.commit()

    async def add_for_today(self, guild_id: int, user_id: int, amount: int) -> int:
        today = date.today().isoformat()
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT xp FROM xp_ledger WHERE guild_id=? AND user_id=? AND day=?",
                (int(guild_id), int(user_id), today),
            ) as cur:
                row = await cur.fetchone()
            cur_xp = int(row[0]) if row else 0
            new_xp = cur_xp + int(amount)
            await db.execute(
                """
                INSERT INTO xp_ledger (guild_id, user_id, day, xp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, day) DO UPDATE SET xp=excluded.xp
                """,
                (int(guild_id), int(user_id), today, int(new_xp)),
            )
            await db.commit()
        return int(new_xp)

    async def get_for_today(self, guild_id: int, user_id: int) -> int:
        today = date.today().isoformat()
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT xp FROM xp_ledger WHERE guild_id=? AND user_id=? AND day=?",
                (int(guild_id), int(user_id), today),
            ) as cur:
                row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def top_week(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT user_id, SUM(xp) AS total
                FROM xp_ledger
                WHERE guild_id=? AND day >= date('now','-6 day')
                GROUP BY user_id
                ORDER BY total DESC
                LIMIT ?
                """,
                (int(guild_id), int(limit)),
            ) as cur:
                rows = await cur.fetchall()
        return [(int(uid), int(total)) for (uid, total) in rows]
