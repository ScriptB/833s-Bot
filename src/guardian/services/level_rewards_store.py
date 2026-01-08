from __future__ import annotations

import aiosqlite


class LevelRewardsStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS level_rewards (
                    guild_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, level, role_id)
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_level_rewards_guild_level ON level_rewards(guild_id, level)")
            await db.commit()

    async def add(self, guild_id: int, level: int, role_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
                (int(guild_id), int(level), int(role_id)),
            )
            await db.commit()

    async def remove(self, guild_id: int, level: int, role_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "DELETE FROM level_rewards WHERE guild_id=? AND level=? AND role_id=?",
                (int(guild_id), int(level), int(role_id)),
            )
            await db.commit()

    async def list(self, guild_id: int) -> list[tuple[int, int]]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT level, role_id FROM level_rewards WHERE guild_id=? ORDER BY level ASC",
                (int(guild_id),),
            ) as cur:
                rows = await cur.fetchall()
        return [(int(lvl), int(rid)) for (lvl, rid) in rows]

    async def roles_for_level(self, guild_id: int, level: int) -> list[int]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT role_id FROM level_rewards WHERE guild_id=? AND level=?",
                (int(guild_id), int(level)),
            ) as cur:
                rows = await cur.fetchall()
        return [int(r[0]) for r in rows]
