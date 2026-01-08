from __future__ import annotations

import aiosqlite
from dataclasses import dataclass


@dataclass(frozen=True)
class LevelsConfig:
    guild_id: int
    enabled: bool
    announce: bool
    xp_min: int
    xp_max: int
    cooldown_seconds: int
    daily_cap: int
    ignore_channels_json: str


class LevelsConfigStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS levels_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    announce INTEGER NOT NULL DEFAULT 1,
                    xp_min INTEGER NOT NULL DEFAULT 10,
                    xp_max INTEGER NOT NULL DEFAULT 20,
                    cooldown_seconds INTEGER NOT NULL DEFAULT 60,
                    daily_cap INTEGER NOT NULL DEFAULT 500,
                    ignore_channels_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            await db.commit()

    async def get(self, guild_id: int) -> LevelsConfig:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT enabled, announce, xp_min, xp_max, cooldown_seconds, daily_cap, ignore_channels_json
                FROM levels_config WHERE guild_id=?
                """,
                (int(guild_id),),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            cfg = LevelsConfig(guild_id, True, True, 10, 20, 60, 500, "[]")
            await self.upsert(cfg)
            return cfg

        return LevelsConfig(
            guild_id=int(guild_id),
            enabled=bool(row[0]),
            announce=bool(row[1]),
            xp_min=int(row[2]),
            xp_max=int(row[3]),
            cooldown_seconds=int(row[4]),
            daily_cap=int(row[5]),
            ignore_channels_json=str(row[6] or "[]"),
        )

    async def upsert(self, cfg: LevelsConfig) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO levels_config (guild_id, enabled, announce, xp_min, xp_max, cooldown_seconds, daily_cap, ignore_channels_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    announce=excluded.announce,
                    xp_min=excluded.xp_min,
                    xp_max=excluded.xp_max,
                    cooldown_seconds=excluded.cooldown_seconds,
                    daily_cap=excluded.daily_cap,
                    ignore_channels_json=excluded.ignore_channels_json
                """,
                (
                    int(cfg.guild_id),
                    int(cfg.enabled),
                    int(cfg.announce),
                    int(cfg.xp_min),
                    int(cfg.xp_max),
                    int(cfg.cooldown_seconds),
                    int(cfg.daily_cap),
                    cfg.ignore_channels_json,
                ),
            )
            await db.commit()
